import pytest

from leveraged_alerts.data import MarketDataError, parse_stooq_csv, parse_yahoo_chart


def test_parse_stooq_csv():
    text = "Date,Open,High,Low,Close\n2026-08-13,3350,3370,3340,3360\n2026-08-14,3360,3390,3350,3380\n"
    bars = parse_stooq_csv(text)
    assert len(bars) == 2
    assert bars[-1].close == 3380.0
    assert bars[-1].date.isoformat() == "2026-08-14"


def test_parse_empty_csv_fails():
    with pytest.raises(MarketDataError, match="empty"):
        parse_stooq_csv("")


def test_parse_wrong_columns_fails():
    with pytest.raises(MarketDataError, match="missing"):
        parse_stooq_csv("foo,bar\n1,2\n")


def test_parse_stooq_rejects_duplicate_dates():
    text = "Date,Close\n2026-08-14,100\n2026-08-14,101\n"
    with pytest.raises(MarketDataError, match="duplicate"):
        parse_stooq_csv(text)


def test_parse_yahoo_chart():
    payload = {
        "chart": {
            "result": [{
                "meta": {"exchangeTimezoneName": "UTC"},
                "timestamp": [1786665600, 1786752000],
                "indicators": {"quote": [{"close": [3360.0, 3380.0]}]},
            }],
            "error": None,
        }
    }
    bars = parse_yahoo_chart(payload)
    assert len(bars) == 2
    assert bars[-1].close == 3380.0


def test_parse_malformed_yahoo_fails():
    with pytest.raises(MarketDataError, match="malformed"):
        parse_yahoo_chart({"chart": {"result": None, "error": {"description": "bad"}}})


def test_parse_yahoo_rejects_duplicate_dates():
    payload = {
        "chart": {
            "result": [{
                "meta": {"exchangeTimezoneName": "UTC"},
                "timestamp": [1786665600, 1786665600],
                "indicators": {"quote": [{"close": [100.0, 101.0]}]},
            }],
            "error": None,
        }
    }
    with pytest.raises(MarketDataError, match="duplicate"):
        parse_yahoo_chart(payload)


def _yahoo_payload(timestamps, closes, timezone="America/New_York"):
    return {
        "chart": {
            "result": [{
                "meta": {"exchangeTimezoneName": timezone},
                "timestamp": timestamps,
                "indicators": {"quote": [{"close": closes}]},
            }],
            "error": None,
        }
    }


def test_parse_yahoo_drops_live_overnight_futures_bar():
    # GC=F completed bars are stamped 00:00 New York. At 20:56 New York the live
    # session bar shares the last completed bar's date (seen nightly from 2026-09-24).
    payload = _yahoo_payload(
        [1790740800, 1790913600, 1791172800, 1791248160],  # 09-30, 10-02, 10-05 00:00, 10-05 20:56
        [4202.3, 4162.3, 4156.8, 4170.0],
    )
    bars = parse_yahoo_chart(payload)
    assert [bar.date.isoformat() for bar in bars] == ["2026-09-30", "2026-10-02", "2026-10-05"]
    assert bars[-1].close == 4156.8


def test_parse_yahoo_keeps_regular_last_bar():
    # ^GSPC bars are stamped 09:30 New York; a regular-time last bar is kept.
    payload = _yahoo_payload([1790861400, 1790947800, 1791207000], [7666.4, 7722.7, 7773.9])
    bars = parse_yahoo_chart(payload)
    assert bars[-1].date.isoformat() == "2026-10-05"
    assert bars[-1].close == 7773.9
