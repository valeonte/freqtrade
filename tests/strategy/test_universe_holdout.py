import json

import numpy as np
import pandas as pd
import pytest

from freqtrade.enums import RunMode
from freqtrade.exceptions import OperationalException
from freqtrade.strategy.holdout import UNLOCK_ENV, check_holdout, touches_holdout
from freqtrade.strategy.universe import point_in_time_universe


def make_frames(days: int = 10, pairs: int = 4) -> tuple[pd.DataFrame, pd.DataFrame]:
    idx = pd.date_range("2026-01-01", periods=days * 48, freq="30min", tz="UTC")
    rng = np.random.default_rng(1)
    close = pd.DataFrame(
        100 * np.exp(np.cumsum(rng.normal(0, 0.01, (len(idx), pairs)), axis=0)),
        index=idx,
        columns=[f"P{i}/USDT" for i in range(pairs)],
    )
    volume = pd.DataFrame(1000.0, index=idx, columns=close.columns)
    return close, volume


class TestUniverse:
    def test_top_n_by_previous_days_volume(self):
        close, volume = make_frames()
        volume["P0/USDT"] = 10.0  # smallest quote volume every day
        u = point_in_time_universe(close, volume, top_n=3, min_days_listed=1)
        assert not u.loc["2026-01-01"].any().any()  # nothing decided before day 1 has ended
        assert not u.loc["2026-01-02":, "P0/USDT"].any()
        assert u.loc["2026-01-02":, ["P1/USDT", "P2/USDT", "P3/USDT"]].all().all()

    def test_uses_yesterday_not_today(self):
        close, volume = make_frames()
        volume.loc["2026-01-05", "P0/USDT"] = 1e9  # huge volume on day 5 only
        u = point_in_time_universe(close, volume, top_n=1, min_days_listed=1)
        assert not u.loc["2026-01-05", "P0/USDT"].any()
        assert u.loc["2026-01-06", "P0/USDT"].all()
        assert not u.loc["2026-01-07", "P0/USDT"].any()

    def test_age_filter_and_delisting(self):
        close, volume = make_frames()
        close.loc[:"2026-01-03", "P1/USDT"] = np.nan  # listed on day 4
        close.loc["2026-01-08":, "P2/USDT"] = np.nan  # delisted after day 7
        u = point_in_time_universe(close, volume, top_n=10, min_days_listed=3)
        assert not u.loc[:"2026-01-06", "P1/USDT"].any()  # 3 days listed by the end of day 6
        assert u.loc["2026-01-07":, "P1/USDT"].all()
        assert not u.loc["2026-01-08":, "P2/USDT"].any()

    def test_range_filter_drops_pegged_coins(self):
        close, volume = make_frames()
        close["P3/USDT"] = 1.0
        u = point_in_time_universe(close, volume, top_n=10, min_days_listed=1)
        assert not u["P3/USDT"].any()


class TestHoldout:
    @pytest.mark.parametrize(
        "timerange,expected",
        [
            ("20260101-20260701", False),
            ("20260101-20260702", True),
            ("20260101-", True),
            (None, True),
        ],
    )
    def test_touches_holdout(self, timerange, expected):
        assert touches_holdout(timerange) is expected

    def test_refused_without_unlock(self, tmp_path, monkeypatch):
        monkeypatch.delenv(UNLOCK_ENV, raising=False)
        config = {"runmode": RunMode.BACKTEST, "timerange": "20260601-20260801", "user_data_dir": tmp_path}
        with pytest.raises(OperationalException, match="holdout"):
            check_holdout(config)

    def test_live_and_early_backtests_pass(self, tmp_path, monkeypatch):
        monkeypatch.delenv(UNLOCK_ENV, raising=False)
        check_holdout({"runmode": RunMode.LIVE, "user_data_dir": tmp_path})
        check_holdout({"runmode": RunMode.BACKTEST, "timerange": "20250101-20260630", "user_data_dir": tmp_path})
        assert not (tmp_path / "holdout_ledger.jsonl").exists()

    def test_unlock_is_logged(self, tmp_path, monkeypatch):
        monkeypatch.setenv(UNLOCK_ENV, "score frozen v35")
        config = {
            "runmode": RunMode.BACKTEST,
            "timerange": "20260701-20261017",
            "user_data_dir": tmp_path,
            "strategy": "FactorStrategy",
            "strategy_settings": {"entry_signal_threshold": 0.9},
        }
        check_holdout(config)
        entry = json.loads((tmp_path / "holdout_ledger.jsonl").read_text())
        assert entry["reason"] == "score frozen v35"
        assert entry["settings"]["strategy_settings"] == {"entry_signal_threshold": 0.9}
