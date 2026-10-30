from itertools import product

import pytest
import requests

from leveraged_alerts import cli, telegram
from leveraged_alerts.config import Settings
from leveraged_alerts.state import load_state, save_state


def message(update_id, text, *, chat_id=123, is_bot=False):
    return {
        "update_id": update_id,
        "message": {"chat": {"id": chat_id}, "from": {"is_bot": is_bot}, "text": text},
    }


@pytest.fixture
def bot(monkeypatch, tmp_path):
    cfg = Settings(assets=(), state_file=tmp_path / "runtime.json")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "123")
    calls = []
    monkeypatch.setattr(cli, "command_run", lambda settings, *, notify: calls.append(("run", notify)) or 0)
    monkeypatch.setattr(cli, "command_summary_telegram", lambda settings: calls.append("summary") or 0)
    monkeypatch.setattr(cli, "send_message", lambda text: calls.append(text))
    return cfg, calls


variants = [
    "".join(letters)
    for word in ("run", "rerun")
    for letters in product(*[(letter.lower(), letter.upper()) for letter in word])
] + ["?", "  RuN\n", "/RUN", "/ReRuN"]


@pytest.mark.parametrize("text", variants)
def test_all_case_combinations_trigger_live_run_and_summary(monkeypatch, bot, text):
    cfg, calls = bot
    monkeypatch.setattr(cli, "get_updates", lambda **kw: [message(10, text)])
    assert cli.command_check_messages(cfg) == 0
    assert calls == [("run", True), "summary"]
    assert load_state(cfg.state_file)["telegram_update_offset"] == 11


@pytest.mark.parametrize("phrase", [
    "again", "retry", "repeat", "refresh", "update", "check", "recheck",
    "status", "summary", "re-run", "run again", "try again", "check again",
    "run it", "run it again", "do it again", "one more time",
])
@pytest.mark.parametrize("style", [str.lower, str.upper, str.title])
def test_natural_rerun_phrases(monkeypatch, bot, phrase, style):
    cfg, calls = bot
    monkeypatch.setattr(cli, "get_updates", lambda **kw: [message(10, style(phrase))])
    assert cli.command_check_messages(cfg) == 0
    assert calls == [("run", True), "summary"]


def test_slash_command_and_extra_whitespace(monkeypatch, bot):
    cfg, calls = bot
    monkeypatch.setattr(cli, "get_updates", lambda **kw: [message(10, " /RuN   It\n AgAiN  ")])
    assert cli.command_check_messages(cfg) == 0
    assert calls == [("run", True), "summary"]


@pytest.mark.parametrize("update", [
    message(10, "run", chat_id=999),
    message(10, "run", is_bot=True),
    message(10, "please run"),
    message(10, "running"),
    message(10, "??"),
    message(10, "hello"),
    message(10, "do not run again"),
    message(10, "don't refresh"),
    message(10, "is everything working again?"),
    message(10, "check tomorrow"),
    {"update_id": 10, "edited_message": message(10, "run")["message"]},
    {"update_id": 10, "message": {"chat": {"id": 123}, "photo": []}},
])
def test_other_chats_bots_and_unrecognized_messages_are_ignored(monkeypatch, bot, update):
    cfg, calls = bot
    monkeypatch.setattr(cli, "get_updates", lambda **kw: [update])
    assert cli.command_check_messages(cfg) == 0
    assert calls == []
    assert load_state(cfg.state_file)["telegram_update_offset"] == 11


def test_queued_commands_coalesce_and_do_not_repeat_after_restart(monkeypatch, bot):
    cfg, calls = bot
    offsets = []

    def updates(*, offset):
        offsets.append(offset)
        return [message(10, "RUN"), message(11, "?")]

    monkeypatch.setattr(cli, "get_updates", updates)
    assert cli.command_check_messages(cfg) == 0
    assert cli.command_check_messages(cfg) == 0
    assert calls == [("run", True), "summary"]
    assert offsets == [0, 12]


def test_live_alert_state_is_preserved_when_saving_cursor(monkeypatch, bot):
    cfg, calls = bot
    monkeypatch.setattr(cli, "get_updates", lambda **kw: [message(10, "rerun")])

    def evaluate(settings, *, notify):
        save_state(settings.state_file, {"assets": {"gold": {"last_alert_event": "SELL"}}})
        return 0

    monkeypatch.setattr(cli, "command_run", evaluate)
    assert cli.command_check_messages(cfg) == 0
    assert load_state(cfg.state_file) == {
        "assets": {"gold": {"last_alert_event": "SELL"}}, "telegram_update_offset": 11,
    }


@pytest.mark.parametrize("failed", ["command_run", "command_summary_telegram"])
def test_market_failure_reports_incomplete_and_consumes_request(monkeypatch, bot, failed):
    cfg, calls = bot
    monkeypatch.setattr(cli, "get_updates", lambda **kw: [message(10, "run")])
    monkeypatch.setattr(cli, failed, lambda *args, **kw: 1)
    assert cli.command_check_messages(cfg) == 1
    assert calls[-1].startswith("RERUN INCOMPLETE")
    assert load_state(cfg.state_file)["telegram_update_offset"] == 11


def test_delivery_failure_leaves_request_for_retry(monkeypatch, bot):
    cfg, calls = bot
    monkeypatch.setattr(cli, "get_updates", lambda **kw: [message(10, "run")])

    def fail(settings):
        raise telegram.TelegramError("delivery failed")

    monkeypatch.setattr(cli, "command_summary_telegram", fail)
    with pytest.raises(telegram.TelegramError):
        cli.command_check_messages(cfg)
    assert "telegram_update_offset" not in load_state(cfg.state_file)


def test_empty_poll_does_not_write_state(monkeypatch, bot):
    cfg, calls = bot
    monkeypatch.setattr(cli, "get_updates", lambda **kw: [])
    assert cli.command_check_messages(cfg) == 0
    assert not cfg.state_file.exists()
    assert calls == []


def test_get_updates_passes_cursor_without_logging_credentials(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "secret-token")
    received = []

    def get(url, **kwargs):
        received.append(kwargs)
        raise requests.ConnectionError(url)

    monkeypatch.setattr(telegram.requests, "get", get)
    with pytest.raises(telegram.TelegramError) as exc:
        telegram.get_updates(offset=11)
    assert received == [{"params": {"offset": 11}, "timeout": 30}]
    assert "secret-token" not in str(exc.value)
    assert exc.value.__suppress_context__


def test_send_failure_does_not_expose_token(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "secret-token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "123")

    def post(url, **kwargs):
        raise requests.ConnectionError(url)

    monkeypatch.setattr(telegram.requests, "post", post)
    with pytest.raises(telegram.TelegramError) as exc:
        telegram.send_message("test")
    assert "secret-token" not in str(exc.value)
    assert exc.value.__suppress_context__
