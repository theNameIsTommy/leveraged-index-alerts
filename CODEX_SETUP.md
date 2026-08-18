# Codex Setup

Use this file when you want Codex to set up the repository with minimal explanation.

## 1. Open the repository

```bash
cd ~/Downloads/leveraged-index-alerts
codex
```

## 2. First Codex prompt

```text
Read README.md, CODEX_SETUP.md, AGENTS.md and VALIDATION.md.

This repo alerts on three independent SMA200 hysteresis strategies:
- Gold: +2% / -2%
- S&P 500: +1% / -1%
- MSCI World proxy: +1% / -1%

Signals must be calculated from the configured unleveraged series.

Check Python 3.11+, git and gh.
Create .venv, install the project in editable mode, run all tests,
and run leveraged-alerts status.

Do not change strategy parameters or symbols during setup.
```

## 3. Publish prompt

```text
Review git status and confirm there are no credentials or unrelated files.
Initialize git if needed.
Create a public GitHub repository named leveraged-index-alerts under my authenticated GitHub account.
Commit the repository and push main.
Do not add Telegram credentials to git.
Stop after the push and tell me the repository URL and the next Telegram setup step.
```

## 4. Telegram setup

Create a bot with `@BotFather`, send `/start` to it, then in your local shell:

```bash
source .venv/bin/activate
read -s TELEGRAM_BOT_TOKEN
export TELEGRAM_BOT_TOKEN
leveraged-alerts chat-id
read TELEGRAM_CHAT_ID
export TELEGRAM_CHAT_ID
printf '%s' "$TELEGRAM_BOT_TOKEN" | gh secret set TELEGRAM_BOT_TOKEN
printf '%s' "$TELEGRAM_CHAT_ID" | gh secret set TELEGRAM_CHAT_ID
```

Do not paste the token into a Codex prompt.

## 5. GitHub workflow test order

Use the workflow inputs in this order:

```text
status
```

Then:

```text
test-telegram
```

Then:

```text
live
```

The first live run bootstraps existing regimes and intentionally sends no historical trade alert.

## 6. Ask Codex to audit it

```text
Audit this alert repo for failure modes.
Focus on missed alerts, duplicate alerts, stale data, future-dated data,
intraday bars, wrong SMA calculations, wrong +1% or +2% boundaries,
and cross-asset state contamination.
Do not optimize the strategy.
Run the full test suite after any fix.
```

## 7. Change the index band later

Do not edit Python. Edit `config/assets.json`.

For example, change S&P 500 from +/-1% to +/-2%:

```json
"upper_band_pct": 2.0,
"lower_band_pct": -2.0
```

Then:

```bash
python -m pytest
leveraged-alerts status
```

A strategy-signature change causes that asset to bootstrap on the next live run rather than sending an old transition.
