import json
from pathlib import Path

import pytest

from leveraged_alerts.config import Settings


def write_config(path: Path, assets: list[dict]):
    path.write_text(json.dumps({"assets": assets}), encoding="utf-8")


def test_default_repo_config_has_requested_three_assets():
    settings = Settings.from_file(Path("config/assets.json"))
    by_id = {asset.id: asset for asset in settings.assets}
    assert set(by_id) == {"gold", "sp500", "world"}
    assert by_id["gold"].upper_band_pct == 2.0
    assert by_id["gold"].lower_band_pct == -2.0
    assert by_id["gold"].provider == "yahoo"
    assert by_id["gold"].symbol == "XAUUSD=X"
    assert by_id["sp500"].upper_band_pct == 1.0
    assert by_id["sp500"].lower_band_pct == -1.0
    assert by_id["world"].upper_band_pct == 1.0
    assert by_id["world"].lower_band_pct == -1.0
    assert by_id["sp500"].symbol == "^GSPC"
    assert by_id["world"].symbol == "SWDA.L"


def test_duplicate_asset_ids_fail(tmp_path):
    path = tmp_path / "assets.json"
    base = {
        "id": "same",
        "name": "Asset",
        "provider": "yahoo",
        "symbol": "ABC",
        "sma_window": 200,
        "upper_band_pct": 1,
        "lower_band_pct": -1,
        "quote_label": "points",
        "signal_description": "test",
        "execution_hint": "test",
    }
    write_config(path, [base, dict(base)])
    with pytest.raises(ValueError, match="unique"):
        Settings.from_file(path)


def test_invalid_band_order_fails(tmp_path):
    path = tmp_path / "assets.json"
    write_config(path, [{
        "id": "x",
        "name": "X",
        "provider": "yahoo",
        "symbol": "X",
        "sma_window": 200,
        "upper_band_pct": -1,
        "lower_band_pct": 1,
        "quote_label": "points",
        "signal_description": "test",
        "execution_hint": "test",
    }])
    with pytest.raises(ValueError, match="below"):
        Settings.from_file(path)


def test_disabled_asset_is_ignored(tmp_path):
    path = tmp_path / "assets.json"
    write_config(path, [{
        "id": "x",
        "name": "X",
        "provider": "yahoo",
        "symbol": "X",
        "sma_window": 200,
        "upper_band_pct": 1,
        "lower_band_pct": -1,
        "quote_label": "points",
        "signal_description": "test",
        "execution_hint": "test",
        "enabled": False,
    }])
    settings = Settings.from_file(path)
    assert settings.assets == ()
