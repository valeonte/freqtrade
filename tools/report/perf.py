"""Time-weighted returns over the report's periods (1D, 1W, 1M, WTD, MTD, YTD)."""

from __future__ import annotations

from datetime import date, timedelta


PERIODS = ["1D", "1W", "1M", "WTD", "MTD", "YTD"]


def index_from_values(values: list[float], flows: list[float], min_value: float = 1.0) -> list[float | None]:
    """Chain daily returns ``(V_t - F_t) / V_{t-1} - 1`` into an index (first funded day = 100).

    Days before the account first holds ``min_value`` USD are ``None``; a later day after an
    empty account restarts from the previous index level.
    """
    out: list[float | None] = []
    level: float | None = None
    prev: float | None = None
    for v, f in zip(values, flows, strict=True):
        if level is None:
            if v >= min_value:
                level = 100.0
            out.append(level)
        else:
            if prev is not None and prev >= min_value:
                level *= (v - f) / prev
            out.append(level)
        prev = v
    return out


def base_date(period: str, asof: date) -> date:
    """The close the period's return is measured from (``asof`` is the last close)."""
    if period == "1D":
        return asof - timedelta(days=1)
    if period == "1W":
        return asof - timedelta(days=7)
    if period == "1M":
        y, m = (asof.year, asof.month - 1) if asof.month > 1 else (asof.year - 1, 12)
        day = min(asof.day, (date(y + (m == 12), m % 12 + 1, 1) - timedelta(days=1)).day)
        return date(y, m, day)
    if period == "WTD":  # weeks start Monday; on a Sunday close this is the whole week
        return asof - timedelta(days=asof.weekday() + 1)
    if period == "MTD":
        return asof.replace(day=1) - timedelta(days=1)
    if period == "YTD":
        return date(asof.year - 1, 12, 31)
    raise ValueError(period)


def period_returns(dates: list[date], index: list[float | None]) -> dict[str, float | None]:
    """Return per period from an index aligned with ``dates`` (ascending); ``None`` if not covered."""
    lookup = dict(zip(dates, index, strict=True))
    asof = dates[-1]
    out: dict[str, float | None] = {}
    for p in PERIODS:
        start, end = lookup.get(base_date(p, asof)), lookup.get(asof)
        out[p] = end / start - 1 if start and end is not None else None
    return out


def period_pnl(dates: list[date], values: list[float], flows: list[float]) -> dict[str, float | None]:
    """USD gain per period: value change minus net deposits."""
    pos = {d: i for i, d in enumerate(dates)}
    asof = dates[-1]
    out: dict[str, float | None] = {}
    for p in PERIODS:
        i = pos.get(base_date(p, asof))
        out[p] = None if i is None else values[-1] - values[i] - sum(flows[i + 1 :])
    return out
