"""Daily performance report of the Binance spot account, by email.

    run_report.sh --mock --out /tmp/report     # sample from a made-up account, no key needed
    run_report.sh --out /tmp/report            # real account, written to files only
    run_report.sh --send                       # real account, emailed

Settings come from the environment, or from ``*.env`` files in ``~/.config/account-report/``
(``KEY=value`` lines; the environment wins): ``FREQTRADE__EXCHANGE__KEY`` /
``FREQTRADE__EXCHANGE__SECRET`` (a read-only key is enough), ``SMTP_USER``,
``SMTP_PASSWORD``, ``SMTP_HOST`` (default smtp.gmail.com), ``SMTP_PORT`` (465),
``REPORT_TO`` (default SMTP_USER) and ``REPORT_ASSETS`` (extra coins to look for trades in).
"""

from __future__ import annotations

import argparse
import base64
import os
import smtplib
import sys
import time
from datetime import UTC, date, datetime, timedelta
from email.message import EmailMessage
from pathlib import Path

from account import AccountData, fetch_closes
from binance import Binance
from charts import line_chart, rebased
from ledger import DAY_MS, USD_STABLES, daily_flows, day_start, holdings_at_day_ends, orders, recent_orders, value
from perf import index_from_values, period_pnl, period_returns
from render import render


CONFIG = Path.home() / ".config" / "account-report"
STATE = Path.home() / ".local" / "state" / "account-report"


def load_settings(folder: Path = CONFIG) -> dict[str, str]:
    """``KEY=value`` lines from every ``*.env`` file in ``folder``; the environment wins."""
    out: dict[str, str] = {}
    for path in sorted(folder.glob("*.env")):
        for line in path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                out[k.strip().removeprefix("export ").strip()] = v.strip().strip("'\"")
    out.update({k: v for k, v in os.environ.items() if k in KEYS})
    return out


KEYS = {
    "FREQTRADE__EXCHANGE__KEY", "FREQTRADE__EXCHANGE__SECRET", "SMTP_USER", "SMTP_PASSWORD", "SMTP_HOST",
    "SMTP_PORT", "REPORT_TO", "REPORT_ASSETS",
}  # fmt: skip


def _d(ms: int) -> date:
    return datetime.fromtimestamp(ms / 1000, UTC).date()


def build(api: Binance, account, closes: dict, days: list[int], now_ms: int, notes: list[str]) -> dict:
    dates = [_d(d) for d in days]
    events = [e for e in account.events() if e.ts <= now_ms]
    held = holdings_at_day_ends(account.balances(), events, days)
    values, missing = [], set()
    for h, d in zip(held, days, strict=False):
        v, miss = value(h, d, closes)
        values.append(v)
        missing |= set(miss)
    if missing:
        notes.append(f"No price for {', '.join(sorted(missing))}; valued at zero.")
    neg = sorted({a for h in held for a, q in h.items() if q < -1e-6})
    if neg:
        notes.append(f"Rebuilt history goes negative in {', '.join(neg)}: some account records are missing.")
    flows = daily_flows(events, days, closes)
    account_index = index_from_values(values, flows)
    btc = [closes["BTC"].get(d) for d in days]
    eth = [closes["ETH"].get(d) for d in days]
    returns = {
        "Account": period_returns(dates, account_index),
        "BTC": period_returns(dates, btc),
        "ETH": period_returns(dates, eth),
    }

    last = held[-1]
    hold = []
    for a, q in last.items():
        p = 1.0 if a in USD_STABLES else closes.get(a, {}).get(days[-1])
        v = q * p if p else 0.0
        if v >= 0.01 or (p is None and q):
            hold.append({"asset": a, "qty": q, "price": p, "value": v})
    total = sum(h["value"] for h in hold) or 1.0
    for h in hold:
        h["weight"] = h["value"] / total
    hold.sort(key=lambda h: h["value"], reverse=True)

    recent = recent_orders(orders(account.fills(), account.symbol_meta()), now_ms)
    for o in recent:
        d = day_start(o["time"])
        p = (
            1.0
            if o["quote"] in USD_STABLES
            else closes.get(o["quote"], {}).get(d) or closes.get(o["quote"], {}).get(d - DAY_MS)
        )
        o["usd"] = o["quote_qty"] * p if p else None
    week = all(o["time"] >= now_ms - 7 * DAY_MS for o in recent) and len(recent) > 5
    series = {"Account": account_index, "BTC": btc, "ETH": eth}
    asof = dates[-1]
    return {
        "asof": asof,
        "value": values[-1],
        "returns": returns,
        "pnl": period_pnl(dates, values, flows),
        "holdings": hold,
        "trades": recent,
        "trades_title": "Trades in the last 7 days" if week else f"Last {len(recent)} trades" if recent else "Trades",
        "charts": {
            "month": _chart(dates[-31:], {k: v[-31:] for k, v in series.items()}, "Last 30 days"),
            "year": _chart(dates[-366:], {k: v[-366:] for k, v in series.items()}, "Last 12 months"),
        },
        "notes": notes,
        "values": dict(zip(dates, values, strict=False)),
    }


def _chart(dates: list[date], series: dict, title: str) -> bytes:
    since, lines = rebased(dates, series)
    if since > dates[0]:
        title = f"Since {since:%d %b %Y}, when the account was funded"
    keep = [i for i, d in enumerate(dates) if d >= since]
    return line_chart([dates[i] for i in keep], {k: [v[i] for i in keep] for k, v in lines.items()},
                      f"{title}, rebased to 100")  # fmt: skip


def check_snapshots(api: Binance, report: dict, closes: dict, notes: list[str]) -> None:
    """Compare the rebuilt daily values with Binance's own daily snapshots of the last month."""
    try:
        snaps = api.snapshots()
    except Exception as e:
        notes.append(f"Couldn't read Binance's snapshots to check the history ({e}).")
        return
    worst = 0.0
    for s in snaps:
        d = day_start(int(s["updateTime"]))
        btc = closes["BTC"].get(d)
        mine = report["values"].get(_d(d))
        if not btc or mine is None:
            continue
        theirs = float(s["data"]["totalAssetOfBtc"]) * btc
        if max(mine, theirs) > 5:
            worst = max(worst, abs(mine - theirs) / max(mine, theirs))
    if worst > 0.02:
        notes.append(f"Rebuilt account values differ from Binance's daily snapshots by up to {worst:.0%}.")


def to_message(subject: str, body_for_cid: str, charts: dict[str, bytes], sender: str, to: str) -> EmailMessage:
    msg = EmailMessage()
    msg["Subject"], msg["From"], msg["To"] = subject, sender, to
    msg.set_content("This report is HTML; open it in a mail client that shows HTML.")
    msg.add_alternative(body_for_cid, subtype="html")
    html_part = msg.get_payload()[1]
    for name, png in charts.items():
        html_part.add_related(png, "image", "png", cid=f"<{name}@account-report>")
    return msg


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--mock", action="store_true", help="made-up account trading BTC/ETH (no key needed)")
    ap.add_argument("--out", type=Path, help="write report.html (images inline), the charts and report.eml here")
    ap.add_argument("--send", action="store_true", help="email the report")
    ap.add_argument("--full-scan", action="store_true", help="look for trades in every symbol again")
    ap.add_argument("--state-dir", type=Path, default=STATE)
    args = ap.parse_args()

    cfg = load_settings()
    now_ms = int(time.time() * 1000)
    asof_ms = day_start(now_ms) - DAY_MS
    asof = _d(asof_ms)
    first = min(date(asof.year - 1, 12, 31), asof - timedelta(days=400))
    start_ms = int(datetime(first.year, first.month, first.day, tzinfo=UTC).timestamp() * 1000)
    days = list(range(start_ms, asof_ms + 1, DAY_MS))
    notes: list[str] = []

    if args.mock:
        from sample_account import MockAccount

        api = Binance()
        closes = fetch_closes(api, {"BTC", "ETH", "BNB"}, start_ms, asof_ms + DAY_MS)
        account = MockAccount(closes, start_ms + 200 * DAY_MS, now_ms)
        notes.append("SAMPLE: made-up account trading BTC/ETH at real prices.")
    else:
        key, secret = cfg.get("FREQTRADE__EXCHANGE__KEY"), cfg.get("FREQTRADE__EXCHANGE__SECRET")
        if not (key and secret):
            print(f"no Binance key: set FREQTRADE__EXCHANGE__KEY/SECRET or put them in {CONFIG}", file=sys.stderr)
            return 2
        api = Binance(key, secret)
        extra = [a.strip() for a in cfg.get("REPORT_ASSETS", "").split(",") if a.strip()]
        account = AccountData(api, args.state_dir, start_ms, extra)
        account.refresh(now_ms, full_scan=args.full_scan)
        closes = fetch_closes(api, account.assets_seen() | {"BTC", "ETH"}, start_ms, asof_ms + DAY_MS)

    report = build(api, account, closes, days, now_ms, notes)
    if not args.mock:
        check_snapshots(api, report, closes, notes)

    subject, body = render(report, {k: f"cid:{k}@account-report" for k in report["charts"]})
    if args.mock:
        subject = "[SAMPLE] " + subject
    sender = cfg.get("SMTP_USER", "account-report@localhost")
    msg = to_message(subject, body, report["charts"], sender, cfg.get("REPORT_TO") or sender)

    if args.out:
        args.out.mkdir(parents=True, exist_ok=True)
        inline = {k: "data:image/png;base64," + base64.b64encode(v).decode() for k, v in report["charts"].items()}
        (args.out / "report.html").write_text(render(report, inline)[1])
        for k, v in report["charts"].items():
            (args.out / f"chart_{k}.png").write_bytes(v)
        (args.out / "report.eml").write_bytes(bytes(msg))
        print(f"{subject}\nwritten to {args.out}", file=sys.stderr)

    if args.send:
        if not cfg.get("SMTP_PASSWORD"):
            print(f"no SMTP_PASSWORD: put SMTP settings in {CONFIG}", file=sys.stderr)
            return 2
        _send(cfg, msg)
        print(f"sent '{subject}' to {msg['To']}", file=sys.stderr)
    return 0


def _send(cfg: dict[str, str], msg: EmailMessage) -> None:
    host, port = cfg.get("SMTP_HOST", "smtp.gmail.com"), int(cfg.get("SMTP_PORT", "465"))
    with smtplib.SMTP_SSL(host, port, timeout=60) as s:
        s.login(cfg["SMTP_USER"], cfg["SMTP_PASSWORD"])
        s.send_message(msg)


def main_or_alert() -> int:
    """Run; if a --send run fails, email the error so a missing report doesn't go unnoticed."""
    try:
        return main()
    except Exception as e:
        if "--send" not in sys.argv:
            raise
        cfg = load_settings()
        msg = EmailMessage()
        msg["Subject"] = "Account report failed"
        msg["From"] = cfg.get("SMTP_USER", "")
        msg["To"] = cfg.get("REPORT_TO") or cfg.get("SMTP_USER", "")
        msg.set_content(f"Today's account report could not be built:\n\n{type(e).__name__}: {e}")
        _send(cfg, msg)
        raise


if __name__ == "__main__":
    sys.exit(main_or_alert())
