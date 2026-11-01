# ruff: noqa: E501, RUF001
"""The report as an HTML email (inline CSS, charts as cid: images)."""

from __future__ import annotations

import html
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from perf import PERIODS


LONDON = ZoneInfo("Europe/London")
UP, DOWN, MUTED, TEXT, LINE = "#0a7a3d", "#c0362c", "#52514e", "#0b0b0b", "#e4e3df"
CELL = f"padding:6px 10px;border-bottom:1px solid {LINE};text-align:right;white-space:nowrap"
HEAD = f"padding:6px 10px;border-bottom:1px solid {MUTED};text-align:right;color:{MUTED};font-weight:600;font-size:12px"


def _pct(x: float | None) -> str:
    if x is None:
        return f'<span style="color:{MUTED}">–</span>'
    color = UP if x > 0 else DOWN if x < 0 else TEXT
    return f'<span style="color:{color}">{x * 100:+.1f}%</span>'


def _usd(x: float | None, signed: bool = False) -> str:
    if x is None:
        return f'<span style="color:{MUTED}">–</span>'
    s = f"{'+' if signed and x > 0 else '-' if x < 0 else ''}${abs(x):,.2f}"
    if not signed:
        return s
    color = UP if x > 0 else DOWN if x < 0 else TEXT
    return f'<span style="color:{color}">{s}</span>'


def _qty(x: float) -> str:
    return f"{x:,.8f}".rstrip("0").rstrip(".") if abs(x) < 1000 else f"{x:,.2f}"


def _price(x: float) -> str:
    return f"{x:,.2f}" if x >= 100 else f"{x:,.4f}" if x >= 1 else f"{x:.8f}".rstrip("0")


def _table(head: list[str], rows: list[list[str]], first_left: bool = True) -> str:
    th = "".join(
        f'<th style="{HEAD};{"text-align:left" if i == 0 and first_left else ""}">{h}</th>' for i, h in enumerate(head)
    )
    body = "".join(
        "<tr>" + "".join(
            f'<td style="{CELL};{"text-align:left" if i == 0 and first_left else ""}">{c}</td>' for i, c in enumerate(r)
        ) + "</tr>"
        for r in rows
    )  # fmt: skip
    return f'<table cellspacing="0" style="border-collapse:collapse;font-size:13px;width:100%">{th and "<tr>" + th + "</tr>"}{body}</table>'


def _section(title: str, inner: str) -> str:
    return f'<h2 style="font-size:15px;margin:28px 0 8px;color:{TEXT}">{title}</h2>{inner}'


def render(r: dict, image_src: dict[str, str]) -> tuple[str, str]:
    """``r`` is the report dict built by report.py; returns (subject, html)."""
    asof = r["asof"]
    one_day = r["returns"]["Account"]["1D"]
    subject = f"Account {asof:%a %d %b}: {_plain_usd(r['value'])}" + (
        f" ({one_day * 100:+.1f}% day)" if one_day is not None else ""
    )

    perf_rows = [[name] + [_pct(r["returns"][name][p]) for p in PERIODS] for name in ("Account", "BTC", "ETH")]
    perf_rows.append(
        [f'<span style="color:{MUTED}">Account P&amp;L</span>'] + [_usd(r["pnl"][p], True) for p in PERIODS]
    )

    hold_rows = [
        [
            h["asset"],
            _qty(h["qty"]),
            _price(h["price"]) if h["price"] else "–",
            _usd(h["value"]),
            f"{h['weight'] * 100:.1f}%",
        ]
        for h in r["holdings"]
    ]

    trade_rows = []
    for o in r["trades"]:
        t = datetime.fromtimestamp(o["time"] / 1000, UTC).astimezone(LONDON)
        side = f'<span style="color:{UP if o["side"] == "BUY" else DOWN}">{o["side"].title()}</span>'
        fees = ", ".join(f"{_qty(q)} {a}" for a, q in o["fees"].items()) or "–"
        trade_rows.append([
            f"{t:%a %d %b %H:%M}", f"{o['base']}/{o['quote']}", side, _qty(o["qty"]), _price(o["price"]),
            _usd(o["usd"]) if o["usd"] is not None else "–", fees,
        ])  # fmt: skip

    notes = "".join(f"<li>{html.escape(n)}</li>" for n in r["notes"])
    body = f"""<!doctype html><html><head><meta charset="utf-8"></head><body style="margin:0;background:#f3f2ef">
<div style="max-width:720px;margin:0 auto;background:#fcfcfb;padding:24px 20px;font-family:-apple-system,Segoe UI,Helvetica,Arial,sans-serif;color:{TEXT}">
<div style="color:{MUTED};font-size:12px">Binance spot account · as of the {asof:%a %d %b %Y} close (00:00 UTC)</div>
<div style="font-size:28px;font-weight:600;margin:4px 0 2px">{_plain_usd(r["value"])}</div>
<div style="font-size:13px;color:{MUTED}">{_pct(one_day)} on the day · {_usd(r["pnl"]["1D"], True)}</div>
{_section("Performance", _table([""] + PERIODS, perf_rows))}
<p style="font-size:11px;color:{MUTED};margin:6px 0 0">Account returns are time-weighted, so deposits and withdrawals don't count as gains. 1M = since the same day last month; WTD weeks start Monday.</p>
<img src="{image_src["month"]}" width="100%" style="max-width:720px;display:block;margin-top:24px" alt="Account, BTC and ETH over the last 30 days, rebased to 100">
<img src="{image_src["year"]}" width="100%" style="max-width:720px;display:block;margin-top:16px" alt="Account, BTC and ETH over the last 12 months, rebased to 100">
{_section("Holdings", _table(["Asset", "Quantity", "Price ($)", "Value", "Weight"], hold_rows))}
{_section(r["trades_title"], _table(["Time (London)", "Pair", "Side", "Quantity", "Avg price", "Value", "Fee"], trade_rows) if trade_rows else f'<p style="color:{MUTED};font-size:13px">No trades yet.</p>')}
{f'<ul style="font-size:11px;color:{MUTED};margin-top:24px;padding-left:16px">{notes}</ul>' if notes else ""}
</div></body></html>"""
    return subject, body


def _plain_usd(x: float) -> str:
    return f"${x:,.2f}"
