# Validation

## Live evidence — 6 October 2026

**Summary:** The nightly pipeline runs on GitHub, all three assets evaluate, and Telegram delivery is confirmed. Gold had failed on 5 of 9 nights from 2026-09-24 and is fixed.

| Check | Result | Evidence |
|---|---|---|
| Scheduled runs fire Tue–Sat | Yes, every expected night since 2026-08-27; start 1–4 h after 01:17 Amsterdam | `gh run list -w alerts.yml` |
| Gold evaluates | Fixed in `9e69d11`. Cause: Yahoo's live overnight GC=F bar shared a date with the last completed bar ("duplicate daily dates") | Runs 35942638503, 36082126780, 36658211455, 36804357991, 36954621656, 37406609407 |
| Missed alert during Gold outage | None. Gold stayed BEAR (about -9% vs SMA200) after the 2026-09-01 SELL | `leveraged-alerts status` |
| GitHub `status` run after fix | Success, all three assets | Run 37508888977 |
| Telegram delivery | `summary-telegram` sent on owner request | Run 37509608906 |
| Offline tests | 45 passed; `compileall` clean | `python -m pytest -q` |

Checklist from the 2–3 October planning notes:

- [x] `python -m pytest -q` and `python -m compileall -q src` pass (45 tests, 2026-10-06).
- [x] Boundary/dead-zone cases keep independent per-asset regimes; repeat runs and restarts do not duplicate alerts. A same-direction alert (BUY after BUY, SELL after SELL) is now refused outright.
- [x] Same-day/intraday, live overnight futures bars, short, stale, future-dated and revised-history inputs cannot create an invalid transition.
- [x] Configured identities match documentation: `GC=F` (USD, COMEX), `^GSPC` (USD), `SWDA.L` (GBp, LSE; label corrected from USD). Provider errors stay visible; failed runs now also send a Telegram failure notice.
- [x] Scheduler and delivery evidence recorded above, separately from unit tests.

### Known data limits

- Yahoo sometimes lists a trading day with no close (SWDA.L: 2026-03-06 and 2026-10-05). No Yahoo endpoint has the value. The messages now show a "Data gap" line and the signal uses the last available close, so it can be one day behind.
- Gold futures roll effect, measured 2005-09 to 2026-10 against GLD (physically backed, no rolls), SMA200 with ±2% bands: mean distance difference +0.17 pp (sd 0.47), same regime on 99.7% of days, 42 transitions each, 40 matched within 30 days and 28 on the same day. No change to the alert source is needed.

Version: 0.2.0

## Local validation

The repository was validated in the build environment with:

```bash
python -m pytest -q
```

Result:

```text
45 passed (2026-10-06)
```

Also validate syntax with:

```bash
python -m compileall -q src
```

## Covered behavior

Automated tests cover:

- Gold +2% / -2% hysteresis.
- S&P 500 and World +1% / -1% hysteresis configuration.
- Exact upper and lower boundary behavior.
- Retaining the prior regime inside the dead zone.
- Independent per-asset state.
- Duplicate alert suppression per asset.
- New-asset and changed-strategy bootstrap behavior.
- Neutral bootstrap followed by the first real transition.
- Same-day/intraday observation exclusion.
- Short history rejection.
- Stale-data rejection.
- Future-date rejection.
- Monotonic transition dates after provider history revisions.
- Stooq CSV parsing.
- Yahoo chart parsing, including dropping Yahoo's live overnight futures bar and reporting dates listed without a close.
- Same-direction alert refusal and LATE ALERT marking.
- Weekly status summary header.
- Asset configuration parsing and validation.
- Disabled asset configuration.
- Heartbeat behavior.

## Network access

The original build environment could not reach Stooq, Yahoo or Telegram. Live data access and Telegram delivery have since been verified from GitHub's runners; see "Live evidence" above.

## Data-series notes

- Gold uses Yahoo `GC=F`, the continuous front-month gold-futures series. It
  is an unleveraged gold proxy rather than spot XAU/USD. Stooq `xauusd` was
  deliberately retired as the active source on 2026-08-26 after its daily
  endpoint returned a JavaScript verification page instead of CSV; it remains
  supported by the adapter for an explicitly configured future use.
- S&P 500 uses Yahoo `^GSPC` as the unleveraged price-index signal.
- World uses Yahoo `SWDA.L` as a practical proxy for MSCI World. SWDA's documented benchmark is MSCI World Index (Net), but an ETF proxy can differ slightly from the exact index because of fund fees, tracking difference and market pricing.

The project never silently substitutes another series if one source fails.
