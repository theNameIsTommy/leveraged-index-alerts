# Validation

Version: 0.2.0

## Local validation

The repository was validated in the build environment with:

```bash
python -m pytest -q
```

Result:

```text
36 passed
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
- Yahoo chart parsing.
- Asset configuration parsing and validation.
- Disabled asset configuration.
- Heartbeat behavior.

## Network limitation of the build environment

The build container used to assemble this ZIP cannot resolve external market-data hosts. Therefore the final live requests to Stooq, Yahoo and Telegram were not executed from this environment.

This is why the GitHub setup sequence begins with a manual `status` workflow. That run validates the exact data access from GitHub's own runner before Telegram is enabled.

## Data-series notes

- Gold uses Yahoo `GC=F`, the continuous front-month gold-futures series. It
  is an unleveraged gold proxy rather than spot XAU/USD. Stooq `xauusd` was
  deliberately retired as the active source on 2026-08-26 after its daily
  endpoint returned a JavaScript verification page instead of CSV; it remains
  supported by the adapter for an explicitly configured future use.
- S&P 500 uses Yahoo `^GSPC` as the unleveraged price-index signal.
- World uses Yahoo `SWDA.L` as a practical proxy for MSCI World. SWDA's documented benchmark is MSCI World Index (Net), but an ETF proxy can differ slightly from the exact index because of fund fees, tracking difference and market pricing.

The project never silently substitutes another series if one source fails.
