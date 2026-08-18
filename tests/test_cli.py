from datetime import date
from pathlib import Path

from leveraged_alerts import cli
from leveraged_alerts.config import AssetSettings, Settings
from leveraged_alerts.models import EventType, Regime, Snapshot
from leveraged_alerts.state import load_state, save_state


def asset(asset_id: str, upper: float, lower: float) -> AssetSettings:
    return AssetSettings(
        id=asset_id,
        name=asset_id.upper(),
        provider="yahoo",
        symbol=f"{asset_id}-symbol",
        sma_window=200,
        upper_band_pct=upper,
        lower_band_pct=lower,
        quote_label="points",
        signal_description="unleveraged test source",
        execution_hint="2x test exposure",
    )


def buy_snapshot(day=date(2026, 8, 14), distance=1.2):
    return Snapshot(
        date=day,
        close=101.2,
        sma=100.0,
        distance_pct=distance,
        regime=Regime.BULL,
        event=EventType.BUY,
    )


def settings(tmp_path: Path) -> Settings:
    return Settings(
        assets=(asset("gold", 2.0, -2.0), asset("sp500", 1.0, -1.0), asset("world", 1.0, -1.0)),
        state_file=tmp_path / "state.json",
    )


def test_first_live_run_bootstraps_each_asset_without_telegram(monkeypatch, tmp_path):
    cfg = settings(tmp_path)
    sent = []
    monkeypatch.setattr(cli, "_load_market", lambda _settings, _asset: [buy_snapshot()])
    monkeypatch.setattr(cli, "send_message", lambda text: sent.append(text))
    monkeypatch.setattr(cli, "_today", lambda _timezone: date(2026, 8, 17))

    assert cli.command_run(cfg, notify=True) == 0
    assert sent == []
    state = load_state(cfg.state_file)
    assert set(state["assets"]) == {"gold", "sp500", "world"}
    assert state["assets"]["sp500"]["strategy_signature"].endswith("u1:l-1")
    assert state["assets"]["gold"]["strategy_signature"].endswith("u2:l-2")


def test_new_sp500_transition_does_not_duplicate_or_touch_other_assets(monkeypatch, tmp_path):
    cfg = Settings(assets=(asset("sp500", 1.0, -1.0), asset("world", 1.0, -1.0)), state_file=tmp_path / "state.json")
    save_state(cfg.state_file, {
        "assets": {
            "sp500": {
                "strategy_signature": "yahoo:sp500-symbol:w200:u1:l-1",
                "last_alert_fingerprint": "sp500:old",
            },
            "world": {
                "strategy_signature": "yahoo:world-symbol:w200:u1:l-1",
                "last_alert_fingerprint": "world:world-symbol:2026-08-14:BUY:w200:u1:l-1",
            },
        },
        "heartbeat_date": "2026-08-01",
    })
    sent = []

    def fake_load(_settings, a):
        return [buy_snapshot()]

    monkeypatch.setattr(cli, "_load_market", fake_load)
    monkeypatch.setattr(cli, "send_message", lambda text: sent.append(text))
    monkeypatch.setattr(cli, "_today", lambda _timezone: date(2026, 8, 17))

    assert cli.command_run(cfg, notify=True) == 0
    assert len(sent) == 1
    assert "SP500 SMA ALERT" in sent[0]

    assert cli.command_run(cfg, notify=True) == 0
    assert len(sent) == 1


def test_strategy_change_for_one_asset_bootstraps_that_asset(monkeypatch, tmp_path):
    changed_asset = asset("sp500", 2.0, -2.0)
    cfg = Settings(assets=(changed_asset,), state_file=tmp_path / "state.json")
    save_state(cfg.state_file, {
        "assets": {
            "sp500": {
                "strategy_signature": "yahoo:sp500-symbol:w200:u1:l-1",
                "last_alert_fingerprint": "old-rule-event",
            }
        }
    })
    sent = []
    monkeypatch.setattr(cli, "_load_market", lambda _settings, _asset: [buy_snapshot(distance=2.2)])
    monkeypatch.setattr(cli, "send_message", lambda text: sent.append(text))
    monkeypatch.setattr(cli, "_today", lambda _timezone: date(2026, 8, 17))

    assert cli.command_run(cfg, notify=True) == 0
    assert sent == []
    state = load_state(cfg.state_file)
    assert state["assets"]["sp500"]["strategy_signature"].endswith("u2:l-2")
