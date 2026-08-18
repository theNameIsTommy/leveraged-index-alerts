from __future__ import annotations

from collections import deque
from datetime import date

from .models import EventType, PriceBar, Regime, Snapshot


class StrategyError(RuntimeError):
    pass


def advance_regime(distance_pct: float, previous: Regime, *, upper: float, lower: float) -> Regime:
    """Apply the hysteresis rule to one completed daily observation."""
    if distance_pct >= upper:
        return Regime.BULL
    if distance_pct <= lower:
        return Regime.BEAR
    return previous


def transition_event(previous: Regime, current: Regime) -> EventType | None:
    if current == previous:
        return None
    if current == Regime.BULL:
        return EventType.BUY
    if current == Regime.BEAR:
        return EventType.SELL
    return None


def build_snapshots(
    bars: list[PriceBar],
    *,
    window: int = 200,
    upper: float = 2.0,
    lower: float = -2.0,
) -> list[Snapshot]:
    if window < 2:
        raise StrategyError("SMA window must be at least 2")
    if lower >= upper:
        raise StrategyError("Lower band must be below upper band")
    if len(bars) < window:
        raise StrategyError(f"Need at least {window} daily observations, got {len(bars)}")

    ordered = sorted(bars, key=lambda bar: bar.date)
    closes: deque[float] = deque()
    rolling_sum = 0.0
    previous_regime = Regime.NEUTRAL
    snapshots: list[Snapshot] = []

    for bar in ordered:
        closes.append(bar.close)
        rolling_sum += bar.close
        if len(closes) > window:
            rolling_sum -= closes.popleft()
        if len(closes) < window:
            continue

        sma = rolling_sum / window
        distance_pct = (bar.close / sma - 1.0) * 100.0
        regime = advance_regime(distance_pct, previous_regime, upper=upper, lower=lower)
        event = transition_event(previous_regime, regime)
        snapshots.append(
            Snapshot(
                date=bar.date,
                close=bar.close,
                sma=sma,
                distance_pct=distance_pct,
                regime=regime,
                event=event,
            )
        )
        previous_regime = regime

    return snapshots


def latest_transition(snapshots: list[Snapshot]) -> Snapshot | None:
    for snapshot in reversed(snapshots):
        if snapshot.event is not None:
            return snapshot
    return None


def validate_freshness(latest_date: date, today: date, max_age_days: int) -> None:
    age = (today - latest_date).days
    if age < 0:
        raise StrategyError(f"Latest market date {latest_date} is in the future relative to {today}")
    if age > max_age_days:
        raise StrategyError(
            f"Latest market data is stale: {latest_date} is {age} calendar days old, "
            f"limit is {max_age_days}"
        )
