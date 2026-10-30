from __future__ import annotations

import os

import requests


class TelegramError(RuntimeError):
    pass


def _token() -> str:
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        raise TelegramError("TELEGRAM_BOT_TOKEN is not set")
    return token


def _chat_id() -> str:
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    if not chat_id:
        raise TelegramError("TELEGRAM_CHAT_ID is not set")
    return chat_id


def send_message(text: str, *, timeout: int = 30) -> None:
    url = f"https://api.telegram.org/bot{_token()}/sendMessage"
    try:
        response = requests.post(
            url,
            json={"chat_id": _chat_id(), "text": text, "disable_web_page_preview": True},
            timeout=timeout,
        )
        response.raise_for_status()
        payload = response.json()
    except (requests.RequestException, ValueError):
        raise TelegramError("Telegram sendMessage failed; check connectivity and bot credentials") from None
    if not payload.get("ok"):
        raise TelegramError("Telegram rejected the message")


def get_updates(*, timeout: int = 30, offset: int | None = None) -> list[dict]:
    url = f"https://api.telegram.org/bot{_token()}/getUpdates"
    params = {"offset": offset} if offset is not None else {}
    try:
        response = requests.get(url, params=params, timeout=timeout)
        response.raise_for_status()
        payload = response.json()
    except (requests.RequestException, ValueError):
        raise TelegramError("Telegram getUpdates failed; check connectivity, credentials and webhook settings") from None
    if not payload.get("ok"):
        raise TelegramError("Telegram rejected getUpdates")
    return payload.get("result") or []
