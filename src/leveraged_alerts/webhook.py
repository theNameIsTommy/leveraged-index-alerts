"""Register a healthy receiver without exposing Telegram credentials."""
from __future__ import annotations

import os
import sys
from urllib.parse import urlsplit

import requests

from .telegram import _token


def configure(origin: str) -> int:
    origin = origin.rstrip("/")
    parsed = urlsplit(origin)
    if (
        parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password
        or parsed.path or parsed.query or parsed.fragment
    ):
        raise ValueError("Receiver must be an HTTPS origin without a path, query or credentials")
    secret = os.environ.get("WEBHOOK_SECRET", "")
    if not secret:
        raise ValueError("WEBHOOK_SECRET is not set")
    token = _token()
    try:
        health = requests.get(origin + "/health", timeout=20)
        health.raise_for_status()
        if health.json().get("ready") is not True:
            raise RuntimeError("Receiver is not configured; Telegram was not changed")
        registered = requests.post(
            f"https://api.telegram.org/bot{token}/setWebhook",
            json={
                "url": origin + "/telegram", "secret_token": secret,
                "allowed_updates": ["message"], "max_connections": 1,
                "drop_pending_updates": False,
            },
            timeout=30,
        )
        registered.raise_for_status()
        if registered.json().get("ok") is not True:
            raise RuntimeError("Telegram rejected webhook registration")
        info = requests.get(f"https://api.telegram.org/bot{token}/getWebhookInfo", timeout=30)
        info.raise_for_status()
        payload = info.json()
        result = payload.get("result") or {}
        if not payload.get("ok") or result.get("url") != origin + "/telegram":
            raise RuntimeError("Telegram webhook URL did not match the requested receiver")
    except (requests.RequestException, ValueError):
        raise RuntimeError("Webhook setup failed; check receiver health and Telegram configuration") from None
    print(f"Telegram webhook registered and verified. Pending updates: {result.get('pending_update_count', 0)}")
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("Usage: python -m leveraged_alerts.webhook https://receiver.example")
    raise SystemExit(configure(sys.argv[1]))
