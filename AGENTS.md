# AGENTS.md

## Purpose

This repository sends Telegram alerts for SMA200 hysteresis regime changes on multiple unleveraged market signals.

## Strategy invariants

Do not change these defaults unless the user explicitly asks:

- Gold: SMA200, +2% BULL boundary, -2% BEAR boundary.
- S&P 500: SMA200, +1% BULL boundary, -1% BEAR boundary.
- MSCI World proxy: SMA200, +1% BULL boundary, -1% BEAR boundary.
- Inside a band's dead zone, retain the previous regime.
- Use completed daily observations only.
- Signal from unleveraged data, never from the leveraged execution product.
- Each asset must have independent state and duplicate suppression.
- A newly added asset or changed strategy signature must bootstrap without sending a historical alert.
- Never silently substitute a different market-data series.
- A failure for one asset should not prevent evaluating the others, but the process should exit non-zero if any asset fails.

## Current signal mapping

- `gold`: Yahoo `GC=F`, continuous front-month gold futures. This is a
  documented unleveraged gold proxy, not spot XAU/USD. Stooq began returning a
  JavaScript verification page rather than daily CSV on 2026-08-26, so it is
  deliberately not the active Gold source.
- `sp500`: Yahoo `^GSPC`, S&P 500 price index.
- `world`: Yahoo `SWDA.L`, iShares Core MSCI World UCITS ETF as a practical unleveraged World proxy.

The World proxy is not claimed to be the exact raw MSCI World index feed. Preserve that documentation unless the provider is deliberately changed and validated.

## Security

Never commit or print:

- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID` if the user considers it sensitive
- GitHub tokens
- other credentials

Use GitHub Actions secrets for Telegram credentials.

## Validation

Run:

```bash
python -m pytest
python -m compileall -q src
```

If network access is available, also run:

```bash
leveraged-alerts status
```

Before changing signal logic, add or update tests first.
