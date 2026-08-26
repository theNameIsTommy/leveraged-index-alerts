from __future__ import annotations

import argparse
from datetime import datetime
from zoneinfo import ZoneInfo

from .config import AssetSettings, Settings
from .data import fetch_daily
from .models import EventType, Snapshot
from .state import asset_state, heartbeat_due, load_state, save_state, should_notify
from .strategy import StrategyError, build_snapshots, latest_transition, validate_freshness
from .telegram import get_updates, send_message


def _today(timezone: str):
    return datetime.now(ZoneInfo(timezone)).date()


def _strategy_signature(asset: AssetSettings) -> str:
    return (
        f"{asset.provider}:{asset.symbol}:w{asset.sma_window}:"
        f"u{asset.upper_band_pct:g}:l{asset.lower_band_pct:g}"
    )


def _load_market(settings: Settings, asset: AssetSettings) -> list[Snapshot]:
    bars = fetch_daily(asset.provider, asset.symbol)
    today = _today(settings.timezone)
    future_dates = [bar.date for bar in bars if bar.date > today]
    if future_dates:
        raise StrategyError(
            f"Latest market date {max(future_dates)} is in the future relative to {today}"
        )
    completed_bars = [bar for bar in bars if bar.date < today]
    snapshots = build_snapshots(
        completed_bars,
        window=asset.sma_window,
        upper=asset.upper_band_pct,
        lower=asset.lower_band_pct,
    )
    latest = snapshots[-1]
    validate_freshness(latest.date, today, settings.max_data_age_days)
    return snapshots


def _position_text(asset: AssetSettings, snapshot: Snapshot) -> str:
    if snapshot.regime.value == "BULL":
        return asset.execution_hint
    if snapshot.regime.value == "BEAR":
        return "cash / leveraged exposure exited"
    return "neutral bootstrap regime"


def _status_text(asset: AssetSettings, snapshot: Snapshot) -> str:
    return (
        f"{asset.name} SMA{asset.sma_window} status\n"
        f"Data date: {snapshot.date.isoformat()}\n"
        f"Signal source: {asset.provider}/{asset.symbol} | {asset.signal_description}\n"
        f"Close: {snapshot.close:,.2f} {asset.quote_label}\n"
        f"SMA{asset.sma_window}: {snapshot.sma:,.2f} {asset.quote_label}\n"
        f"Distance: {snapshot.distance_pct:+.2f}%\n"
        f"Buy boundary: {asset.upper_band_pct:+.2f}%\n"
        f"Sell boundary: {asset.lower_band_pct:+.2f}%\n"
        f"Regime: {snapshot.regime.value}\n"
        f"Position interpretation: {_position_text(asset, snapshot)}"
    )


def _alert_text(asset: AssetSettings, event_snapshot: Snapshot, current: Snapshot) -> str:
    action = "BUY / ENTER LEVERAGED REGIME" if event_snapshot.event == EventType.BUY else "SELL / EXIT LEVERAGED REGIME"
    return (
        f"{asset.name.upper()} SMA ALERT: {action}\n\n"
        f"Transition date: {event_snapshot.date.isoformat()}\n"
        f"Close: {event_snapshot.close:,.2f} {asset.quote_label}\n"
        f"SMA{asset.sma_window}: {event_snapshot.sma:,.2f} {asset.quote_label}\n"
        f"Distance at transition: {event_snapshot.distance_pct:+.2f}%\n"
        f"Buy boundary: {asset.upper_band_pct:+.2f}%\n"
        f"Sell boundary: {asset.lower_band_pct:+.2f}%\n"
        f"New regime: {event_snapshot.regime.value}\n\n"
        f"Latest available data: {current.date.isoformat()}, distance {current.distance_pct:+.2f}%\n"
        f"Signal source: {asset.provider}/{asset.symbol} | {asset.signal_description}\n"
        f"Execution reference: {asset.execution_hint}\n\n"
        "Rules alert only. Verify the market and your execution instrument before trading."
    )


def command_status(settings: Settings) -> int:
    errors = 0
    for index, asset in enumerate(settings.assets):
        if index:
            print("\n" + "=" * 72 + "\n")
        try:
            snapshots = _load_market(settings, asset)
        except Exception as exc:
            errors += 1
            print(f"{asset.name}: ERROR: {exc}")
            continue
        print(_status_text(asset, snapshots[-1]))
        transition = latest_transition(snapshots)
        if transition:
            print(f"\nMost recent transition: {transition.event.value} on {transition.date.isoformat()}")
    return 1 if errors else 0


def command_run(settings: Settings, *, notify: bool) -> int:
    state = load_state(settings.state_file)
    today = _today(settings.timezone)
    changed = False
    errors = 0

    for asset in settings.assets:
        try:
            snapshots = _load_market(settings, asset)
            current = snapshots[-1]
            transition = latest_transition(snapshots)
            print(_status_text(asset, current))

            if not notify:
                if transition is None:
                    print("No historical band transition is available yet.\n")
                    continue
                fingerprint = transition.fingerprint(
                    asset_id=asset.id,
                    symbol=asset.symbol,
                    window=asset.sma_window,
                    upper=asset.upper_band_pct,
                    lower=asset.lower_band_pct,
                )
                print(f"Dry run. Latest transition fingerprint: {fingerprint}\n")
                continue

            fingerprint = transition.fingerprint(
                asset_id=asset.id,
                symbol=asset.symbol,
                window=asset.sma_window,
                upper=asset.upper_band_pct,
                lower=asset.lower_band_pct,
            ) if transition else None
            per_asset = asset_state(state, asset.id)
            signature = _strategy_signature(asset)
            if (
                per_asset.get("strategy_signature") != signature
                or "last_alert_fingerprint" not in per_asset
            ):
                per_asset["strategy_signature"] = signature
                per_asset["last_alert_fingerprint"] = fingerprint
                per_asset["last_alert_event_date"] = transition.date.isoformat() if transition else None
                per_asset["bootstrapped"] = True
                changed = True
                print(f"{asset.name}: bootstrapped without sending a historical alert.\n")
            elif transition is None:
                print("No historical band transition is available yet.\n")
            elif should_notify(fingerprint, per_asset, event_date=transition.date):
                send_message(_alert_text(asset, transition, current))
                per_asset["last_alert_fingerprint"] = fingerprint
                per_asset["last_alert_event_date"] = transition.date.isoformat()
                per_asset["bootstrapped"] = False
                changed = True
                print(f"{asset.name}: Telegram {transition.event.value} alert sent for {transition.date}.\n")
            else:
                print(f"{asset.name}: no new regime transition.\n")
        except Exception as exc:
            errors += 1
            print(f"{asset.name}: ERROR: {exc}\n")

    if notify and heartbeat_due(state, today, every_days=28):
        state["heartbeat_date"] = today.isoformat()
        changed = True
        print("Updated the 28-day repository heartbeat marker.")

    if notify and changed:
        save_state(settings.state_file, state)
    return 1 if errors else 0


def command_test_telegram(settings: Settings) -> int:
    lines = ["TEST MESSAGE", "", "Leveraged SMA alert bot is connected.", "", "Configured assets:"]
    for asset in settings.assets:
        lines.append(
            f"- {asset.name}: SMA{asset.sma_window}, "
            f"{asset.upper_band_pct:+.1f}% / {asset.lower_band_pct:+.1f}%, {asset.provider}/{asset.symbol}"
        )
    send_message("\n".join(lines))
    print("Telegram test message sent.")
    return 0


def command_chat_id() -> int:
    updates = get_updates()
    found: dict[str, str] = {}
    for update in updates:
        message = update.get("message") or update.get("channel_post") or {}
        chat = message.get("chat") or {}
        if "id" in chat:
            label = chat.get("username") or chat.get("title") or chat.get("first_name") or "chat"
            found[str(chat["id"])] = str(label)
    if not found:
        print("No chats found. Open your bot in Telegram, send /start, then run this command again.")
        return 1
    print("Telegram chats visible to this bot:")
    for chat_id, label in found.items():
        print(f"  {chat_id}  {label}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Multi-asset SMA200 hysteresis alerts")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("status", help="Print all configured asset statuses without sending anything")
    run = sub.add_parser("run", help="Evaluate all configured assets and optionally send new transition alerts")
    run.add_argument("--notify", action="store_true", help="Actually send Telegram and update runtime state")
    sub.add_parser("test-telegram", help="Send a Telegram test message with the configured assets")
    sub.add_parser("chat-id", help="Show Telegram chat IDs from recent bot updates")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    settings = Settings.from_env()

    if args.command == "status":
        return command_status(settings)
    if args.command == "run":
        return command_run(settings, notify=args.notify)
    if args.command == "test-telegram":
        return command_test_telegram(settings)
    if args.command == "chat-id":
        return command_chat_id()
    parser.error(f"Unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
