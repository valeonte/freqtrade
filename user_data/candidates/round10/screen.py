"""
Round 10 screens: each study's feature panel through round 8's `study48_screen.py` unchanged (study 44's screen with
the circular-shift null), pointed at this round's cache. Rules in README.md, fixed before running.

    nice -n 19 .env/bin/python user_data/candidates/round10/screen.py build 56|57|58|59
    nice -n 19 .env/bin/python user_data/candidates/round10/screen.py screen 56|57|58|59   # -> results_<fam>_*.csv
"""

import sys
from pathlib import Path


HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "round8"))
import r10data as R  # noqa: E402
import study48_screen as S48  # noqa: E402


class _Shim:
    """What study48_screen reads from round 8's data module."""

    CACHE = R.CACHE
    group_of = staticmethod(R.group_of)


S48.R = _Shim
S48.OUT = HERE
for fam in R.FAMILIES:
    S48.SAMPLES[fam] = S48.SAMPLES["main"]


def screen(fam: str) -> None:
    S48.screen(fam)
    for f in HERE.glob(f"results_48_{fam}_*"):  # study48_screen's file names -> results_<fam>_*
        f.replace(HERE / f.name.replace(f"results_48_{fam}_", f"results_{fam}_"))


if __name__ == "__main__":
    if sys.argv[1] == "build":
        R.build(sys.argv[2])
    else:
        screen(sys.argv[2])
