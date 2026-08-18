from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class AssetSettings:
    id: str
    name: str
    provider: str
    symbol: str
    sma_window: int
    upper_band_pct: float
    lower_band_pct: float
    quote_label: str
    signal_description: str
    execution_hint: str
    enabled: bool = True

    def validate(self) -> None:
        if not self.id or not self.id.replace("_", "").replace("-", "").isalnum():
            raise ValueError(f"Invalid asset id: {self.id!r}")
        if self.provider not in {"stooq", "yahoo"}:
            raise ValueError(f"Asset {self.id}: provider must be stooq or yahoo")
        if not self.symbol:
            raise ValueError(f"Asset {self.id}: symbol cannot be empty")
        if self.sma_window < 2:
            raise ValueError(f"Asset {self.id}: sma_window must be at least 2")
        if self.lower_band_pct >= self.upper_band_pct:
            raise ValueError(f"Asset {self.id}: lower_band_pct must be below upper_band_pct")


@dataclass(frozen=True)
class Settings:
    assets: tuple[AssetSettings, ...]
    max_data_age_days: int = 5
    timezone: str = "Europe/Amsterdam"
    state_file: Path = Path("state/runtime.json")
    asset_config_file: Path = Path("config/assets.json")

    @classmethod
    def from_env(cls) -> "Settings":
        path = Path(os.getenv("ASSET_CONFIG", "config/assets.json"))
        settings = cls.from_file(
            path,
            max_data_age_days=int(os.getenv("MAX_DATA_AGE_DAYS", "5")),
            timezone=os.getenv("TIMEZONE", "Europe/Amsterdam").strip(),
            state_file=Path(os.getenv("STATE_FILE", "state/runtime.json")),
        )
        return settings

    @classmethod
    def from_file(
        cls,
        path: Path,
        *,
        max_data_age_days: int = 5,
        timezone: str = "Europe/Amsterdam",
        state_file: Path = Path("state/runtime.json"),
    ) -> "Settings":
        try:
            payload: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError(f"Could not read asset config {path}: {exc}") from exc

        raw_assets = payload.get("assets")
        if not isinstance(raw_assets, list) or not raw_assets:
            raise ValueError("Asset config must contain a non-empty 'assets' list")

        assets: list[AssetSettings] = []
        for raw in raw_assets:
            if not isinstance(raw, dict):
                raise ValueError("Each asset config entry must be an object")
            asset = AssetSettings(
                id=str(raw.get("id", "")).strip(),
                name=str(raw.get("name", "")).strip(),
                provider=str(raw.get("provider", "")).strip().lower(),
                symbol=str(raw.get("symbol", "")).strip(),
                sma_window=int(raw.get("sma_window", 200)),
                upper_band_pct=float(raw.get("upper_band_pct", 0.0)),
                lower_band_pct=float(raw.get("lower_band_pct", 0.0)),
                quote_label=str(raw.get("quote_label", "")).strip(),
                signal_description=str(raw.get("signal_description", "")).strip(),
                execution_hint=str(raw.get("execution_hint", "")).strip(),
                enabled=bool(raw.get("enabled", True)),
            )
            asset.validate()
            assets.append(asset)

        ids = [asset.id for asset in assets]
        if len(ids) != len(set(ids)):
            raise ValueError("Asset ids must be unique")
        if max_data_age_days < 0:
            raise ValueError("MAX_DATA_AGE_DAYS cannot be negative")
        if not timezone:
            raise ValueError("TIMEZONE cannot be empty")

        return cls(
            assets=tuple(asset for asset in assets if asset.enabled),
            max_data_age_days=max_data_age_days,
            timezone=timezone,
            state_file=state_file,
            asset_config_file=path,
        )
