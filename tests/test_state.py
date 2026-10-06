from datetime import date

from leveraged_alerts.state import asset_state, heartbeat_due, last_alert_event, should_notify


def test_duplicate_alert_is_suppressed_per_asset():
    state = {}
    sp = asset_state(state, "sp500")
    world = asset_state(state, "world")
    sp["last_alert_fingerprint"] = "sp-event"
    world["last_alert_fingerprint"] = "world-event"
    assert not should_notify("sp-event", sp)
    assert should_notify("new-sp-event", sp)
    assert not should_notify("world-event", world)


def test_asset_states_are_independent():
    state = {}
    asset_state(state, "gold")["last_alert_fingerprint"] = "gold"
    asset_state(state, "sp500")["last_alert_fingerprint"] = "sp"
    assert asset_state(state, "gold")["last_alert_fingerprint"] == "gold"
    assert asset_state(state, "sp500")["last_alert_fingerprint"] == "sp"


def test_empty_fingerprint_never_notifies():
    assert not should_notify(None, {})


def test_older_reconstructed_transition_does_not_notify():
    state = {
        "last_alert_fingerprint": "newer-event",
        "last_alert_event_date": "2026-08-14",
    }
    assert not should_notify("different-older-event", state, event_date=date(2026, 8, 13))


def test_later_reconstructed_transition_notifies():
    state = {
        "last_alert_fingerprint": "older-event",
        "last_alert_event_date": "2026-08-14",
    }
    assert should_notify("different-newer-event", state, event_date=date(2026, 8, 15))


def test_heartbeat_due_when_missing():
    assert heartbeat_due({}, date(2026, 8, 17), every_days=28)


def test_heartbeat_not_due_too_soon():
    state = {"heartbeat_date": "2026-08-01"}
    assert not heartbeat_due(state, date(2026, 8, 17), every_days=28)


def test_heartbeat_due_after_28_days():
    state = {"heartbeat_date": "2026-07-20"}
    assert heartbeat_due(state, date(2026, 8, 17), every_days=28)


def test_malformed_heartbeat_is_treated_as_due():
    state = {"heartbeat_date": "not-a-date"}
    assert heartbeat_due(state, date(2026, 8, 17), every_days=28)


def test_same_direction_reconstructed_transition_does_not_notify():
    state = {
        "last_alert_fingerprint": "gold:GC=F:2026-09-01:SELL:w200:u2:l-2",
        "last_alert_event_date": "2026-09-01",
    }
    # Revised history moved the SELL one day later: not a new regime change.
    assert not should_notify(
        "gold:GC=F:2026-09-02:SELL:w200:u2:l-2", state, event_date=date(2026, 9, 2), event="SELL"
    )
    assert should_notify(
        "gold:GC=F:2026-10-02:BUY:w200:u2:l-2", state, event_date=date(2026, 10, 2), event="BUY"
    )


def test_last_alert_event_prefers_stored_value():
    assert last_alert_event({"last_alert_event": "BUY", "last_alert_fingerprint": "x:SELL:y"}) == "BUY"
    assert last_alert_event({"last_alert_fingerprint": None}) is None
