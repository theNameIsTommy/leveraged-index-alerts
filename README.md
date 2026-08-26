# Leveraged Index Alerts

A small, free GitHub Actions project that watches three unleveraged market signals and sends Telegram notifications when an SMA200 hysteresis strategy changes regime.

Default assets:

| Asset | Signal series | SMA | Buy band | Sell band | Example leveraged execution |
|---|---|---:|---:|---:|---|
| Gold | Yahoo `GC=F` continuous gold futures | 200 days | +2% | -2% | WisdomTree Gold 2x Daily Leveraged, LBUL |
| S&P 500 | Yahoo `^GSPC` | 200 days | +1% | -1% | Your preferred 2x S&P 500 product |
| MSCI World proxy | Yahoo `SWDA.L` | 200 days | +1% | -1% | Amundi MSCI World (2x) Leveraged UCITS ETF, LVWC |

The signal is always calculated from an unleveraged underlying index or unleveraged proxy. It is never calculated from the 2x product itself.

## The rule

For each asset:

```text
distance % = (daily close / SMA200 - 1) * 100

at or above upper band -> BULL / leveraged regime
inside the band         -> keep previous regime
at or below lower band  -> BEAR / exit leveraged regime
```

Defaults:

```text
Gold:       +2% / -2%
S&P 500:    +1% / -1%
World:      +1% / -1%
```

This is hysteresis, not a normal moving-average crossover. Once an asset enters BULL, falling back inside the band does not create a sell. It must cross the lower boundary. The reverse is true after a sell.

Example for the S&P 500:

```text
S&P 500 reaches +1.1% above SMA200 -> BUY / enter leveraged regime
falls to +0.2%                     -> HOLD existing leveraged regime
falls to -0.8%                     -> still HOLD
falls to -1.0%                     -> SELL / exit leveraged regime
```

The project uses completed daily observations only. It does not generate intraday signals.

## Is a 1% index band a good idea?

It is a reasonable starting configuration, but this repo does not claim that 1% is mathematically optimal.

A narrower band reacts sooner when a trend changes, but it also produces more whipsaws around SMA200. A wider 2% or 3% band reacts later but filters more noise. The right comparison is therefore empirical.

The intended backtest sweep for broad indexes is:

```text
0%       plain SMA200 crossover
0.5%     very responsive hysteresis
1%       default in this alert repo
2%       stronger whipsaw filter
3%       slow, conservative filter
```

Keep the live alert at 1% until the backtest gives a reason to change it. If you change a band in `config/assets.json`, the alert state automatically re-bootstraps that asset so an old historical transition is not sent as a fresh alert.

## Why SWDA.L for World?

The ideal signal would be the exact MSCI World index series used by the leveraged product. A clean, unrestricted daily historical feed for that index is not as easy to obtain for a free GitHub project.

The default therefore uses `SWDA.L`, the London listing of the iShares Core MSCI World UCITS ETF, as a practical unleveraged proxy. BlackRock states that SWDA benchmarks the MSCI World Index (Net). The signal source is deliberately documented so it is not confused with the exact MSCI index.

For the example leveraged execution product, LVWC tracks a leveraged MSCI World benchmark. The alert still uses the unleveraged World proxy, not LVWC itself.

If a better free exact-index feed becomes available, replace only the World `provider` and `symbol` in `config/assets.json`, then validate signal dates against the backtest before relying on it.

## What happens each day

```text
Gold XAU/USD      S&P 500 ^GSPC      World SWDA.L
      |                 |                 |
      +-----------------+-----------------+
                        |
                        v
              download daily closes
                        |
                        v
                 calculate SMA200
                        |
                        v
             calculate distance from SMA
                        |
                        v
        reconstruct each asset's own regime
                        |
                        v
       compare each latest transition with state
                        |
             +----------+----------+
             |                     |
         no change             new transition
             |                     |
       no notification       Telegram notification
```

Each asset has independent regime history and independent duplicate suppression. Gold can be BULL while the S&P 500 is BEAR and World is BULL.

## Repository structure

```text
config/assets.json                    assets, data sources and bands
.github/workflows/alerts.yml          scheduled and manual GitHub Action
.github/workflows/ci.yml              automated tests
src/leveraged_alerts/config.py        config loader and validation
src/leveraged_alerts/data.py          Stooq and Yahoo data adapters
src/leveraged_alerts/strategy.py      SMA and hysteresis logic
src/leveraged_alerts/telegram.py      Telegram Bot API client
src/leveraged_alerts/state.py         per-asset duplicate suppression
src/leveraged_alerts/cli.py           command-line interface
tests/                                unit tests
state/runtime.json                    small committed runtime state
AGENTS.md                             project rules for Codex
CODEX_SETUP.md                        shortest Codex setup path
VALIDATION.md                         validation notes
```

## Configure assets

Edit `config/assets.json`.

Example S&P 500 entry:

```json
{
  "id": "sp500",
  "name": "S&P 500",
  "provider": "yahoo",
  "symbol": "^GSPC",
  "sma_window": 200,
  "upper_band_pct": 1.0,
  "lower_band_pct": -1.0,
  "quote_label": "points",
  "signal_description": "Unleveraged S&P 500 price index daily close",
  "execution_hint": "2x S&P 500 exposure chosen by the investor"
}
```

To test a 2% band later:

```json
"upper_band_pct": 2.0,
"lower_band_pct": -2.0
```

No Python change is needed.

## 1. Local setup on your Mac

```bash
cd ~/Downloads/leveraged-index-alerts
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
python -m pytest
```

Check all three current signals:

```bash
leveraged-alerts status
```

The old command is retained as an alias for convenience:

```bash
gold-sma-alert status
```

It now prints all configured assets, not only gold.

## 2. Set this up with Codex

From the repository root:

```bash
codex
```

Then paste:

```text
Read README.md, CODEX_SETUP.md, AGENTS.md and VALIDATION.md.

Explain the three-asset alert architecture briefly.
Then check Python, git and GitHub CLI on this Mac.
Create a virtual environment, install the project in editable mode,
run all tests, and run leveraged-alerts status.

Do not change the trading rules or data symbols unless a test or setup problem requires it.
```

For a focused safety review:

```text
Review this repo for anything that could cause a missed, duplicated, stale,
intraday, mathematically incorrect, or cross-asset signal.

Preserve these defaults:
Gold SMA200 +/-2%.
S&P 500 SMA200 +/-1%.
MSCI World proxy SMA200 +/-1%.
Signals must use unleveraged series.
Run the full test suite after any change.
```

OpenAI documents Codex CLI as a terminal coding agent that can inspect, modify and run code in a local repository. See the official Codex CLI documentation linked in the Sources section.

## 3. Create the GitHub repository

If this folder is not already a Git repository:

```bash
git init
git branch -M main
git add .
git commit -m "Initial leveraged index alerts"
```

Authenticate GitHub CLI if needed:

```bash
gh auth login
```

Create and push a public repository:

```bash
gh repo create leveraged-index-alerts --public --source=. --remote=origin --push
```

Or tell Codex:

```text
Check git status and make sure no secrets are present.
If gh is authenticated, create a public GitHub repository named leveraged-index-alerts,
commit the intended files, and push main.
Do not add Telegram credentials to git.
```

## 4. Create the Telegram bot

In Telegram:

1. Open the official `@BotFather` account.
2. Send `/newbot`.
3. Choose a display name and username.
4. Save the bot token securely.
5. Open the new bot and send `/start`.

Never commit the token.

## 5. Find your Telegram chat ID

With the virtual environment active:

```bash
read -s TELEGRAM_BOT_TOKEN
export TELEGRAM_BOT_TOKEN
leveraged-alerts chat-id
```

After you see the chat ID:

```bash
read TELEGRAM_CHAT_ID
export TELEGRAM_CHAT_ID
```

## 6. Add GitHub Actions secrets

```bash
printf '%s' "$TELEGRAM_BOT_TOKEN" | gh secret set TELEGRAM_BOT_TOKEN
printf '%s' "$TELEGRAM_CHAT_ID" | gh secret set TELEGRAM_CHAT_ID
```

Only the secret names appear in the repository. The values are not committed.

## 7. Test GitHub Actions safely

In GitHub, open:

```text
Actions -> Leveraged Index Alerts -> Run workflow
```

Use this sequence:

### First: `status`

Downloads all three signal series and prints the latest regimes. It sends no Telegram message and changes no state.

### Second: `test-telegram`

Sends a test message listing all configured assets and bands.

### Third: `live`

The first live evaluation bootstraps each asset independently. It records the most recent known transition without sending a historical BUY or SELL.

After bootstrap, a future transition sends Telegram.

## 8. Scheduled operation

The workflow runs Tuesday through Saturday at 01:17 in `Europe/Amsterdam`.

The schedule is intentionally after both the London session and the prior US trading session. It also avoids the start of the hour.

GitHub supports timezone-aware schedules using IANA timezone names. GitHub also warns that scheduled workflows in public repositories can be disabled after 60 days with no repository activity. The project keeps a small heartbeat in `state/runtime.json` approximately every 28 days and commits it when needed.

## Telegram alert examples

S&P 500 BUY:

```text
S&P 500 SMA ALERT: BUY / ENTER LEVERAGED REGIME

Transition date: 2026-...
Close: ... points
SMA200: ... points
Distance at transition: +1.08%
Buy boundary: +1.00%
Sell boundary: -1.00%
New regime: BULL
```

Gold SELL:

```text
GOLD SMA ALERT: SELL / EXIT LEVERAGED REGIME

Distance at transition: -2.11%
Buy boundary: +2.00%
Sell boundary: -2.00%
New regime: BEAR
```

## Data-source safety

The repo deliberately does not silently fall back from one signal series to another.

If Yahoo fails for gold, gold fails for that run.

If Yahoo fails for S&P 500 or World, the affected asset fails for that run. The other assets are still evaluated, and the overall command exits non-zero so GitHub visibly marks the run as problematic.

That behavior is intentional. A silent data-source substitution can change an SMA signal.

Yahoo's chart endpoint is a practical free source used by this project, but it is not treated as a contractual market-data API. The code validates parsing, minimum history, positivity, duplicate dates and freshness before using the data.

## Why the exact signal series matters

Do not calculate these signals from the leveraged product price.

A daily 2x ETF or ETC has path-dependent compounding. Its own SMA200 can diverge materially from the underlying index SMA200. The strategy is therefore:

```text
unleveraged market signal -> decide regime -> execute with leveraged product
```

not:

```text
leveraged product price -> calculate trend signal
```

## Changing or adding an asset

You can add Nasdaq-100, Euro Stoxx 50, DAX or another broad market without changing strategy code. Add another object to `config/assets.json` with a unique `id`, unleveraged data symbol and its own bands.

Then run:

```bash
python -m pytest
leveraged-alerts status
```

The first `live` run for a newly added asset bootstraps only that asset.

## Validation status

Version 0.2 has automated tests covering:

- gold +/-2% hysteresis
- equity-index +/-1% hysteresis
- exact boundary behavior
- independent per-asset regimes
- independent duplicate suppression
- strategy-change bootstrap behavior
- short history
- stale data
- future-dated data
- Stooq parsing
- Yahoo parsing
- asset-config parsing and validation
- disabled assets
- heartbeat behavior

See `VALIDATION.md` for the latest local validation result.

## Sources

Official/reference pages used when choosing and documenting the defaults:

- S&P Dow Jones Indices, S&P 500: https://www.spglobal.com/spdji/en/indices/equity/sp-500/
- iShares Core MSCI World UCITS ETF, SWDA: https://www.ishares.com/uk/individual/en/products/251882/SWDA
- GitHub scheduled workflows: https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows
- OpenAI Codex CLI: https://help.openai.com/en/articles/11096431

The World execution example LVWC is documented by its exchange listing and issuer materials as a leveraged MSCI World product. Always verify the exact product facts with the issuer before trading.

## Disclaimer

This repository implements a rules-based alert. It is not personalized investment advice and does not place orders. Leveraged products can lose value rapidly and daily leverage creates path-dependent returns. Verify every live alert and the exact execution product before trading.
