from __future__ import annotations

import csv
import io
from datetime import date, datetime
from urllib.parse import quote
from zoneinfo import ZoneInfo

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .models import PriceBar

STOOQ_DAILY_URL = "https://stooq.com/q/d/l/"


class MarketDataError(RuntimeError):
    pass


def _session() -> requests.Session:
    retry = Retry(
        total=3,
        connect=3,
        read=3,
        backoff_factor=0.8,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset({"GET"}),
    )
    session = requests.Session()
    session.headers.update({"User-Agent": "leveraged-index-alerts/0.2"})
    session.mount("https://", HTTPAdapter(max_retries=retry))
    return session


def parse_stooq_csv(text: str) -> list[PriceBar]:
    if not text.strip():
        raise MarketDataError("Stooq returned an empty response")

    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames or "Date" not in reader.fieldnames or "Close" not in reader.fieldnames:
        raise MarketDataError("Stooq CSV is missing Date or Close columns")

    bars: list[PriceBar] = []
    for row in reader:
        raw_date = (row.get("Date") or "").strip()
        raw_close = (row.get("Close") or "").strip()
        if not raw_date or not raw_close or raw_close in {"N/D", "."}:
            continue
        try:
            bar_date = date.fromisoformat(raw_date)
            close = float(raw_close)
        except ValueError:
            continue
        if close <= 0:
            continue
        bars.append(PriceBar(date=bar_date, close=close))

    deduped = {bar.date: bar for bar in bars}
    result = sorted(deduped.values(), key=lambda bar: bar.date)
    if not result:
        raise MarketDataError("No valid daily observations were found in the Stooq response")
    return result


def fetch_stooq_daily(symbol: str, *, timeout: int = 30) -> list[PriceBar]:
    try:
        response = _session().get(
            STOOQ_DAILY_URL,
            params={"s": symbol, "i": "d"},
            timeout=timeout,
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        raise MarketDataError(f"Could not download {symbol} daily data from Stooq: {exc}") from exc
    return parse_stooq_csv(response.text)


def parse_yahoo_chart(payload: dict) -> list[PriceBar]:
    try:
        result = payload["chart"]["result"][0]
        timestamps = result["timestamp"]
        closes = result["indicators"]["quote"][0]["close"]
        timezone_name = result.get("meta", {}).get("exchangeTimezoneName") or "UTC"
    except (KeyError, IndexError, TypeError) as exc:
        error = payload.get("chart", {}).get("error") if isinstance(payload, dict) else None
        raise MarketDataError(f"Yahoo chart response is malformed: {error or exc}") from exc

    try:
        timezone = ZoneInfo(timezone_name)
    except Exception:
        timezone = ZoneInfo("UTC")

    bars: list[PriceBar] = []
    for timestamp, raw_close in zip(timestamps, closes):
        if raw_close is None:
            continue
        try:
            close = float(raw_close)
            bar_date = datetime.fromtimestamp(int(timestamp), tz=timezone).date()
        except (TypeError, ValueError, OSError):
            continue
        if close > 0:
            bars.append(PriceBar(date=bar_date, close=close))

    deduped = {bar.date: bar for bar in bars}
    result_bars = sorted(deduped.values(), key=lambda bar: bar.date)
    if not result_bars:
        raise MarketDataError("No valid daily observations were found in the Yahoo response")
    return result_bars


def fetch_yahoo_daily(symbol: str, *, timeout: int = 30) -> list[PriceBar]:
    encoded = quote(symbol, safe="")
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{encoded}"
    try:
        response = _session().get(
            url,
            params={
                "range": "3y",
                "interval": "1d",
                "events": "history",
                "includeAdjustedClose": "false",
            },
            timeout=timeout,
        )
        response.raise_for_status()
        payload = response.json()
    except (requests.RequestException, ValueError) as exc:
        raise MarketDataError(f"Could not download {symbol} daily data from Yahoo: {exc}") from exc
    return parse_yahoo_chart(payload)


def fetch_daily(provider: str, symbol: str, *, timeout: int = 30) -> list[PriceBar]:
    provider = provider.lower().strip()
    if provider == "stooq":
        return fetch_stooq_daily(symbol, timeout=timeout)
    if provider == "yahoo":
        return fetch_yahoo_daily(symbol, timeout=timeout)
    raise MarketDataError(f"Unsupported data provider: {provider}")
