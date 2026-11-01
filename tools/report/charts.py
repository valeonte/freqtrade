"""PNG charts for the email: account vs BTC vs ETH, rebased to 100."""

from __future__ import annotations

import io
from datetime import date

import matplotlib


matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt


SURFACE = "#fcfcfb"
TEXT = "#0b0b0b"
MUTED = "#52514e"
GRID = "#e4e3df"
SERIES = {"Account": "#2a78d6", "BTC": "#eb6834", "ETH": "#1baf7a"}


def rebased(dates: list[date], series: dict[str, list[float | None]]) -> tuple[date, dict[str, list]]:
    """Each series over its value on the first date where every series has one, times 100.

    An account funded part-way through the window starts the chart there, so all lines share a start.
    """
    since = next((d for i, d in enumerate(dates) if all(v[i] for v in series.values())), dates[-1])
    out = {}
    for name, vals in series.items():
        base = next((v for d, v in zip(dates, vals, strict=False) if d >= since and v), None)
        out[name] = [(v / base * 100 if v and base and d >= since else None) for d, v in zip(dates, vals, strict=False)]
    return since, out


def line_chart(dates: list[date], series: dict[str, list[float | None]], title: str) -> bytes:
    fig, ax = plt.subplots(figsize=(7.2, 3.4), dpi=150)
    fig.patch.set_facecolor(SURFACE)
    ax.set_facecolor(SURFACE)
    ends = []
    for name, vals in series.items():
        pts = [(d, v) for d, v in zip(dates, vals, strict=False) if v is not None]
        if not pts:
            continue
        xs, ys = zip(*pts, strict=False)
        ax.plot(xs, ys, color=SERIES[name], lw=2 if name == "Account" else 1.5, label=name, solid_capstyle="round")
        ends.append([ys[-1], ys[-1], name, xs[-1]])
    # end labels, pushed apart so they don't overlap
    lo, hi = ax.get_ylim()
    gap = (hi - lo) * 0.07
    ends.sort()
    for i in range(1, len(ends)):
        ends[i][1] = max(ends[i][1], ends[i - 1][1] + gap)
    for y, label_y, name, _x in ends:
        ax.text(1.01, label_y, f"{name} {y - 100:+.1f}%", transform=ax.get_yaxis_transform(), va="center",
                fontsize=8, color=TEXT)  # fmt: skip
    ax.axhline(100, color=MUTED, lw=0.8, ls=(0, (2, 2)))
    ax.set_title(title, loc="left", fontsize=11, color=TEXT, pad=22)
    ax.grid(axis="y", color=GRID, lw=0.8)
    ax.tick_params(colors=MUTED, labelsize=8, length=0)
    for s in ax.spines.values():
        s.set_visible(False)
    span = (dates[-1] - dates[0]).days
    ax.xaxis.set_major_locator(mdates.AutoDateLocator(minticks=4, maxticks=8))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%d %b" if span < 120 else "%b %y"))
    ax.margins(x=0.01)
    ax.legend(
        loc="lower left",
        bbox_to_anchor=(0, 1.0),
        frameon=False,
        fontsize=8,
        labelcolor=TEXT,
        ncol=3,
        borderaxespad=0,
        handlelength=1.5,
    )
    fig.subplots_adjust(left=0.07, right=0.83, top=0.82, bottom=0.1)
    buf = io.BytesIO()
    fig.savefig(buf, format="png", facecolor=SURFACE)
    plt.close(fig)
    return buf.getvalue()
