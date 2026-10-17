"""
Compare a dry-run (paper) bot's trades with a backtest of the same days.

Reads the dry-run database, refreshes the candles, backtests the same config from the day of the
first paper trade to now, and matches trades by pair and entry day. Prints a report, writes it to
`user_data/paper/reports/`, and exits 1 if any trade is missing on either side.

    .env/bin/python user_data/paper/reconcile.py -c user_data/paper/config_btc_eth_trend_dry.json
"""

import argparse
import json
import sqlite3
import subprocess
import sys
import tempfile
import zipfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pandas as pd


EMPTY = pd.DataFrame(
    {c: pd.Series(dtype="datetime64[ns, UTC]") for c in ("open_date", "close_date")}
    | {c: pd.Series(dtype=float) for c in ("open_rate", "close_rate", "profit_ratio")}
    | {"pair": pd.Series(dtype=str)}
)


def paper_trades(db_path: Path) -> pd.DataFrame:
    with sqlite3.connect(f"file:{db_path}?mode=ro", uri=True) as db:
        t = pd.read_sql(
            "select pair, open_date, close_date, open_rate, close_rate, close_profit as profit_ratio,"
            " is_open, exit_reason from trades",
            db,
        )
    for col in ("open_date", "close_date"):
        t[col] = pd.to_datetime(t[col], utc=True, format="mixed")
    return t


def backtest_trades(config: Path, datadir: str, since: datetime, pairs: list[str]) -> pd.DataFrame:
    ft = [sys.executable, "-m", "freqtrade"]
    tf = json.loads(config.read_text()).get("timeframe", "1d")
    warmup = (since - timedelta(days=400)).strftime("%Y%m%d")
    subprocess.run(
        [
            *ft,
            "download-data",
            "-c",
            str(config),
            "--datadir",
            datadir,
            "-t",
            tf,
            "--timerange",
            f"{warmup}-",
            "-p",
            *pairs,
        ],
        check=True,
        capture_output=True,
    )
    with tempfile.TemporaryDirectory() as out:
        run = subprocess.run(
            [
                *ft,
                "backtesting",
                "-c",
                str(config),
                "--datadir",
                datadir,
                "--timerange",
                f"{since:%Y%m%d}-",
                "--export",
                "trades",
                "--backtest-directory",
                out,
            ],
            capture_output=True,
            text=True,
        )
        if run.returncode != 0:
            if "No data left after adjusting for startup candles" in run.stdout + run.stderr:
                return EMPTY.copy()  # no candle has closed inside the window yet
            raise RuntimeError(f"backtest failed:\n{run.stdout[-2000:]}{run.stderr[-2000:]}")
        zf = zipfile.ZipFile(sorted(Path(out).glob("*.zip"))[-1])
        name = next(n for n in zf.namelist() if n.endswith(".json") and "config" not in n and "market" not in n)
        result = json.load(zf.open(name))["strategy"]
    t = pd.DataFrame(next(iter(result.values()))["trades"])
    if t.empty:
        return EMPTY.copy()
    for col in ("open_date", "close_date"):
        t[col] = pd.to_datetime(t[col], utc=True)
    return t


def reconcile(paper: pd.DataFrame, bt: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    for t in (paper, bt):
        t["day"] = t["open_date"].dt.floor("D")
    m = paper.merge(bt, on=["pair", "day"], how="outer", suffixes=("_paper", "_bt"), indicator=True)
    matched = m[m["_merge"] == "both"].copy()
    matched["entry_diff_bps"] = (matched["open_rate_paper"] / matched["open_rate_bt"] - 1) * 1e4
    matched["exit_diff_bps"] = (matched["close_rate_paper"] / matched["close_rate_bt"] - 1) * 1e4
    return matched, m[m["_merge"] == "left_only"], m[m["_merge"] == "right_only"]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("-c", "--config", type=Path, required=True)
    ap.add_argument("--datadir", default="user_data/data_bed/binance")
    ap.add_argument("--since", help="YYYYMMDD; default: the day of the first paper trade")
    args = ap.parse_args()

    cfg = json.loads(args.config.read_text())
    db = Path(cfg["db_url"].removeprefix("sqlite:///"))
    paper = paper_trades(db)
    if paper.empty and not args.since:
        print(f"No paper trades in {db} yet.")
        return 0
    since = (
        datetime.strptime(args.since, "%Y%m%d").replace(tzinfo=UTC)
        if args.since
        else paper["open_date"].min().floor("D").to_pydatetime()
    )
    bt = backtest_trades(args.config, args.datadir, since, cfg["exchange"]["pair_whitelist"])
    matched, paper_only, bt_only = reconcile(paper, bt)

    lines = [
        f"# Paper vs backtest, {cfg.get('bot_name', args.config.stem)}, {datetime.now(UTC):%Y-%m-%d %H:%M} UTC",
        "",
        f"Window from {since:%Y-%m-%d}. Paper trades {len(paper)}, backtest trades {len(bt)}, "
        f"matched {len(matched)} (same pair, same entry day), paper only {len(paper_only)}, "
        f"backtest only {len(bt_only)}.",
        "",
    ]
    if len(matched):
        cols = [
            "pair",
            "day",
            "open_rate_paper",
            "open_rate_bt",
            "entry_diff_bps",
            "close_rate_paper",
            "close_rate_bt",
            "exit_diff_bps",
            "profit_ratio_paper",
            "profit_ratio_bt",
        ]
        lines += ["## Matched", "", matched[cols].round(4).to_markdown(index=False), ""]
        lines.append(
            f"Mean entry slippage {matched['entry_diff_bps'].mean():+.1f} bps, "
            f"mean exit slippage {matched['exit_diff_bps'].mean():+.1f} bps (paper vs backtest fill)."
        )
        lines.append("")
    for title, df, side in (("Paper only", paper_only, "paper"), ("Backtest only", bt_only, "bt")):
        if len(df):
            lines += [
                f"## {title}",
                "",
                df[["pair", "day", f"open_rate_{side}", f"close_rate_{side}"]]
                .round({f"open_rate_{side}": 4, f"close_rate_{side}": 4})
                .to_markdown(index=False),
                "",
            ]
    report = "\n".join(lines)
    print(report)
    out = Path("user_data/paper/reports") / f"{args.config.stem}-{datetime.now(UTC):%Y%m%d-%H%M}.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(report)
    return 1 if len(paper_only) or len(bt_only) else 0


if __name__ == "__main__":
    sys.exit(main())
