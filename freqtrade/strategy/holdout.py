"""
Holdout lock for strategy research.

Candles from `HOLDOUT_START` up to `HOLDOUT_END` (the day the holdout was set aside) are kept
away from research: a backtest or hyperopt whose timerange overlaps them is refused. Later
candles are free, so paper trades can be compared with a backtest of the same days. A strategy
that has been frozen can be scored on the holdout by setting the environment variable
`FT_HOLDOUT_UNLOCK` to the reason, which is then appended, with the config's strategy settings,
to `user_data/holdout_ledger.jsonl`. Every look at the holdout is on that ledger, so it is clear
how many times the data has been used.
"""

import hashlib
import json
import logging
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from freqtrade.configuration import TimeRange
from freqtrade.enums.runmode import OPTIMIZE_MODES
from freqtrade.exceptions import OperationalException


logger = logging.getLogger(__name__)

HOLDOUT_START = datetime(2026, 7, 1, tzinfo=UTC)
HOLDOUT_END = datetime(2026, 10, 17, tzinfo=UTC)
UNLOCK_ENV = "FT_HOLDOUT_UNLOCK"


def touches_holdout(timerange: str | None) -> bool:
    """True if the timerange overlaps the holdout (a missing start or end counts as unbounded)."""
    if not timerange:
        return True
    tr = TimeRange.parse_timerange(timerange)
    starts_before_end = tr.startts == 0 or tr.startts < HOLDOUT_END.timestamp()
    ends_after_start = tr.stopts == 0 or tr.stopts > HOLDOUT_START.timestamp()
    return starts_before_end and ends_after_start


def check_holdout(config: dict[str, Any]) -> None:
    """Refuse a research run that reaches into the holdout, unless it is unlocked and logged."""
    if config.get("runmode") not in OPTIMIZE_MODES:
        return
    if not touches_holdout(config.get("timerange")):
        return
    reason = os.environ.get(UNLOCK_ENV, "").strip()
    if not reason:
        raise OperationalException(
            f"Timerange {config.get('timerange') or '(none)'} reaches into the holdout "
            f"({HOLDOUT_START:%Y-%m-%d} to {HOLDOUT_END:%Y-%m-%d}). End it on or before "
            f"{HOLDOUT_START:%Y%m%d}, start it on or after {HOLDOUT_END:%Y%m%d}, "
            f"or set {UNLOCK_ENV}=<reason> to score a frozen strategy."
        )
    settings = {
        "strategy": config.get("strategy"),
        "timeframe": config.get("timeframe"),
        "strategy_settings": config.get("strategy_settings"),
        "strategy_factor_mix": config.get("strategy_factor_mix"),
    }
    entry = {
        "at": datetime.now(UTC).isoformat(timespec="seconds"),
        "reason": reason,
        "runmode": str(config.get("runmode")),
        "timerange": config.get("timerange"),
        "config_files": config.get("config_files"),
        "settings_sha256": hashlib.sha256(
            json.dumps(settings, sort_keys=True).encode()
        ).hexdigest(),
        "settings": settings,
    }
    ledger = Path(config.get("user_data_dir", "user_data")) / "holdout_ledger.jsonl"
    with ledger.open("a") as f:
        f.write(json.dumps(entry, default=str) + "\n")
    logger.warning("HOLDOUT UNLOCKED (%s); logged to %s", reason, ledger)
