import pytest

from leveraged_alerts import cli
from leveraged_alerts.config import Settings
from leveraged_alerts.state import load_state, save_state


@pytest.fixture
def rerun(monkeypatch, tmp_path):
    settings = Settings(assets=(), state_file=tmp_path / "runtime.json")
    calls = []
    monkeypatch.setattr(cli, "command_run", lambda cfg, *, notify: calls.append("live") or 0)
    monkeypatch.setattr(cli, "command_summary_telegram", lambda cfg: calls.append("summary") or 0)
    monkeypatch.setattr(cli, "send_message", lambda text: calls.append(text))
    return settings, calls


def test_request_retries_do_not_repeat_summary_or_alerts(rerun):
    settings, calls = rerun
    assert cli.command_webhook_run(settings, update_id=12) == 0
    assert cli.command_webhook_run(settings, update_id=10) == 0
    assert cli.command_webhook_run(settings, update_id=12) == 0
    assert calls == ["live", "summary", "live", "summary"]
    assert load_state(settings.state_file)["telegram_webhook_updates"] == [12, 10]


def test_request_preserves_alert_state_and_bounds_saved_ids(monkeypatch, rerun):
    settings, calls = rerun
    save_state(settings.state_file, {"telegram_webhook_updates": list(range(100))})

    def evaluate(cfg, *, notify):
        state = load_state(cfg.state_file)
        state["assets"] = {"gold": {"last_alert_event": "SELL"}}
        save_state(cfg.state_file, state)
        return 0

    monkeypatch.setattr(cli, "command_run", evaluate)
    assert cli.command_webhook_run(settings, update_id=100) == 0
    state = load_state(settings.state_file)
    assert state["telegram_webhook_updates"] == list(range(1, 101))
    assert state["assets"]["gold"]["last_alert_event"] == "SELL"


def test_delivery_error_does_not_mark_request_processed(monkeypatch, rerun):
    settings, calls = rerun

    def fail(cfg):
        raise RuntimeError("delivery failed")

    monkeypatch.setattr(cli, "command_summary_telegram", fail)
    with pytest.raises(RuntimeError):
        cli.command_webhook_run(settings, update_id=10)
    assert "telegram_webhook_updates" not in load_state(settings.state_file)


def test_failed_asset_does_not_silence_summary_or_failure_notice(monkeypatch, rerun):
    settings, calls = rerun
    monkeypatch.setattr(cli, "command_run", lambda cfg, *, notify: 1)
    assert cli.command_webhook_run(settings, update_id=10) == 1
    assert calls[0] == "summary"
    assert calls[1].startswith("RERUN INCOMPLETE")
    assert load_state(settings.state_file)["telegram_webhook_updates"] == [10]


def test_negative_request_id_is_rejected(rerun):
    settings, calls = rerun
    with pytest.raises(ValueError):
        cli.command_webhook_run(settings, update_id=-1)
    assert calls == []
