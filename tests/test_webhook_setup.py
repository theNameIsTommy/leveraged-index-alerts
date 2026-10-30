import pytest
import requests

from leveraged_alerts import webhook


class Reply:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self.payload


def test_registration_preserves_pending_messages_and_checks_active_url(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test-token")
    monkeypatch.setenv("WEBHOOK_SECRET", "test-secret")
    calls = []

    def get(url, **kw):
        calls.append(url)
        if url.endswith("/health"):
            return Reply({"ready": True})
        return Reply({"ok": True, "result": {"url": "https://receiver.test/telegram", "pending_update_count": 1}})

    def post(url, *, json, **kw):
        calls.append(url)
        assert json["drop_pending_updates"] is False
        assert json["secret_token"] == "test-secret"
        assert json["allowed_updates"] == ["message"]
        assert json["max_connections"] == 1
        return Reply({"ok": True})

    monkeypatch.setattr(webhook.requests, "get", get)
    monkeypatch.setattr(webhook.requests, "post", post)
    assert webhook.configure("https://receiver.test/") == 0
    assert calls[0].endswith("/health")
    assert calls[1].endswith("/setWebhook")
    assert calls[2].endswith("/getWebhookInfo")


@pytest.mark.parametrize("origin", ["http://receiver.test", "https://user:password@receiver.test", "https://receiver.test/path", "https://receiver.test?token=secret", "https://receiver.test#secret"])
def test_unsafe_origins_fail_before_network(monkeypatch, origin):
    monkeypatch.setattr(webhook.requests, "get", lambda *a, **kw: pytest.fail("network request"))
    with pytest.raises(ValueError):
        webhook.configure(origin)


def test_unhealthy_receiver_does_not_change_telegram(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test-token")
    monkeypatch.setenv("WEBHOOK_SECRET", "test-secret")
    monkeypatch.setattr(webhook.requests, "get", lambda *a, **kw: Reply({"ready": False}))
    monkeypatch.setattr(webhook.requests, "post", lambda *a, **kw: pytest.fail("registration request"))
    with pytest.raises(RuntimeError, match="not configured"):
        webhook.configure("https://receiver.test")


def test_network_errors_do_not_expose_credentials(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test-token")
    monkeypatch.setenv("WEBHOOK_SECRET", "test-secret")
    monkeypatch.setattr(webhook.requests, "get", lambda *a, **kw: Reply({"ready": True}))

    def fail(url, **kw):
        raise requests.ConnectionError(url)

    monkeypatch.setattr(webhook.requests, "post", fail)
    with pytest.raises(RuntimeError) as exc:
        webhook.configure("https://receiver.test")
    assert "test-token" not in str(exc.value)
    assert exc.value.__suppress_context__
