from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any


class StateError(RuntimeError):
    pass


def load_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        raw = path.read_text(encoding="utf-8").strip()
        return json.loads(raw) if raw else {}
    except (OSError, json.JSONDecodeError) as exc:
        raise StateError(f"Could not read state file {path}: {exc}") from exc


def save_state(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(path)


def asset_state(state: dict[str, Any], asset_id: str) -> dict[str, Any]:
    assets = state.setdefault("assets", {})
    value = assets.setdefault(asset_id, {})
    if not isinstance(value, dict):
        value = {}
        assets[asset_id] = value
    return value


def should_notify(fingerprint: str | None, per_asset_state: dict[str, Any]) -> bool:
    return bool(fingerprint) and fingerprint != per_asset_state.get("last_alert_fingerprint")


def heartbeat_due(state: dict[str, Any], today: date, *, every_days: int = 28) -> bool:
    raw = state.get("heartbeat_date")
    if not raw:
        return True
    try:
        previous = date.fromisoformat(str(raw))
    except ValueError:
        return True
    return (today - previous).days >= every_days
