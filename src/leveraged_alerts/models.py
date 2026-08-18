from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import Enum


class Regime(str, Enum):
    NEUTRAL = "NEUTRAL"
    BULL = "BULL"
    BEAR = "BEAR"


class EventType(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


@dataclass(frozen=True)
class PriceBar:
    date: date
    close: float


@dataclass(frozen=True)
class Snapshot:
    date: date
    close: float
    sma: float
    distance_pct: float
    regime: Regime
    event: EventType | None = None

    def fingerprint(
        self,
        *,
        asset_id: str,
        symbol: str,
        window: int,
        upper: float,
        lower: float,
    ) -> str | None:
        if self.event is None:
            return None
        return (
            f"{asset_id}:{symbol}:{self.date.isoformat()}:{self.event.value}:"
            f"w{window}:u{upper:g}:l{lower:g}"
        )
