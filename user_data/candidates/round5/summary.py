"""
Round 5's final table: each study's primary setting (and its best-looking variant) against the bot
alone, from the results files the study scripts write. No new computation.

    .env/bin/python user_data/candidates/round5/summary.py
"""

from pathlib import Path

import pandas as pd


HERE = Path(__file__).parent
P = ("2019-20", "2021-23", "2024-26H1")


def pick(path: str, candidate: str, variants: list[str]) -> list[dict]:
    t = pd.read_csv(HERE / path)
    out = []
    for v in variants:
        r = t[(t["candidate"] == candidate) & (t["variant"] == v)]
        if r.empty:
            continue
        r = r.iloc[0]
        out.append(
            {
                "study": path.removeprefix("results_").removesuffix(".csv").replace("_", " "),
                "row": v,
                **{p: f"{r[f'{p} sh']:.2f} / {r[f'{p} dd']:.0%}" for p in P},
                "all": f"{r['all sh']:.2f} / {r['all dd']:.0%}",
                "beats bot": bool(r["beats_bot"]) if "alone" not in v else "",
            }
        )
    return out


def main() -> None:
    rows = []
    for path, cand in (
        ("results_33.csv", "primary 60s/1h"),
        ("results_34.csv", "spike +10% 3d"),
        ("results_35_bybit.csv", "primary 60s/1h"),
        ("results_35_coinbase.csv", "primary 60s/1h"),
        ("results_36.csv", "primary 60s/24h"),
        ("results_38.csv", "primary 60s/24h"),
    ):
        if not (HERE / path).exists():
            continue
        short = "c" if path == "results_34.csv" else cand
        rows += pick(path, cand, [f"{short} alone", f"bot + 20% {short}", f"bot + overlay {short}"])
    t37 = pd.read_csv(HERE / "results_37.csv")
    for v in ("bot + n20 a0.5 continuous", "bot + walk-forward"):
        r = t37[t37["variant"] == v].iloc[0]
        rows.append(
            {
                "study": "37",
                "row": v,
                **{p: f"{r[f'{p} sh']:.2f} / {r[f'{p} dd']:.0%}" for p in P},
                "all": f"{r['all sh']:.2f} / {r['all dd']:.0%}",
                "beats bot": bool(r["beats_bot"]),
            }
        )
    tab = pd.DataFrame(rows)
    print("| study | row | " + " | ".join(P) + " | 2019-Jun 2026 | passes condition 1 |")
    print("|---|---|---|---|---|---|---|")
    for _, r in tab.iterrows():
        print(f"| {r['study']} | {r['row']} | " + " | ".join(r[p] for p in P) + f" | {r['all']} | {r['beats bot']} |")


if __name__ == "__main__":
    main()
