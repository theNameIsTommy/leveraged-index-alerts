from datetime import date, timedelta

import pytest

from leveraged_alerts.models import EventType, PriceBar, Regime
from leveraged_alerts.strategy import (
    StrategyError,
    advance_regime,
    build_snapshots,
    latest_transition,
    transition_event,
    validate_freshness,
)


def test_gold_hysteresis_keeps_previous_regime_inside_two_percent_band():
    assert advance_regime(1.99, Regime.BULL, upper=2.0, lower=-2.0) == Regime.BULL
    assert advance_regime(-1.99, Regime.BEAR, upper=2.0, lower=-2.0) == Regime.BEAR


def test_index_hysteresis_keeps_previous_regime_inside_one_percent_band():
    assert advance_regime(0.99, Regime.BULL, upper=1.0, lower=-1.0) == Regime.BULL
    assert advance_regime(-0.99, Regime.BEAR, upper=1.0, lower=-1.0) == Regime.BEAR
    assert advance_regime(0.0, Regime.NEUTRAL, upper=1.0, lower=-1.0) == Regime.NEUTRAL


def test_index_upper_boundary_enters_bull_at_exactly_one_percent():
    assert advance_regime(1.0, Regime.BEAR, upper=1.0, lower=-1.0) == Regime.BULL


def test_index_lower_boundary_enters_bear_at_exactly_minus_one_percent():
    assert advance_regime(-1.0, Regime.BULL, upper=1.0, lower=-1.0) == Regime.BEAR


def test_gold_boundaries_remain_two_percent():
    assert advance_regime(2.0, Regime.BEAR, upper=2.0, lower=-2.0) == Regime.BULL
    assert advance_regime(-2.0, Regime.BULL, upper=2.0, lower=-2.0) == Regime.BEAR


def test_transition_events():
    assert transition_event(Regime.BEAR, Regime.BULL) == EventType.BUY
    assert transition_event(Regime.BULL, Regime.BEAR) == EventType.SELL
    assert transition_event(Regime.BULL, Regime.BULL) is None


def test_short_history_fails():
    bars = [PriceBar(date(2026, 1, 1), 100.0)]
    with pytest.raises(StrategyError, match="Need at least"):
        build_snapshots(bars, window=200)


def test_build_snapshots_generates_transition():
    start = date(2025, 1, 1)
    bars = [PriceBar(start + timedelta(days=i), 100.0) for i in range(200)]
    bars.append(PriceBar(start + timedelta(days=200), 102.5))
    snapshots = build_snapshots(bars, window=200, upper=1.0, lower=-1.0)
    assert snapshots[-1].regime == Regime.BULL
    assert snapshots[-1].event == EventType.BUY
    assert latest_transition(snapshots) == snapshots[-1]


def test_freshness_accepts_recent_data():
    validate_freshness(date(2026, 8, 14), date(2026, 8, 17), 5)


def test_freshness_rejects_stale_data():
    with pytest.raises(StrategyError, match="stale"):
        validate_freshness(date(2026, 8, 1), date(2026, 8, 17), 5)


def test_freshness_rejects_future_data():
    with pytest.raises(StrategyError, match="future"):
        validate_freshness(date(2026, 8, 18), date(2026, 8, 17), 5)
