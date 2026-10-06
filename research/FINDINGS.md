# Band research findings — 6 October 2026

Source: `research/backtest.py`, full tables in `RESULTS.md`. In-sample history only, after modelled costs
(2x daily reset, T-bill + 0.5% financing, 0.6% fee, 0.15% per switch, one-day execution lag).

## Summary

- **S&P 500 and MSCI World: keep ±1%.** Band width between 0.5% and 2% barely changes risk-adjusted
  results (S&P Sharpe 0.56–0.58, World 0.40–0.46). This is the broad plateau the handover asked for;
  ±1% sits inside it. Bands mainly cut switches (S&P 6.6 → 2.9 a year) and cost drag (1.1 → 0.5 pp a year).
- **Gold: the ±2% band is not special, and the gold trend filter itself is weak.** No band beat plain
  1x gold on Sharpe (0.54). The live ±2% rule lost up to 68% versus 46% for unleveraged gold, mostly in
  the 2011–15 bear market, where repeated failed rallies at 2x lost 57%. Treat 2x gold as the least
  validated of the three.
- **ATR-style bands: no consistent edge.** 1×ATR helped gold (Sharpe 0.53) but not S&P or World. The
  gain is within noise and adds complexity. Not recommended to switch.
- **The filter's value is drawdown control, not return.** S&P: worst loss 40% versus 88% for always-2x,
  with a similar or better CAGR. World: 57% versus 85%.

## Risks the filter does not remove

- **One-day crashes.** In 1987 the World strategy lost 40%, worse than unleveraged buy-and-hold (−23%),
  because it was 2x when the crash hit and the signal reacts a day later.
- **Choppy bears.** In 2022, S&P at ±1% lost 27% versus 25% for unleveraged buy-and-hold.
- ±3% scores best for S&P, but it is the edge of the tested grid and has only 1 switch a year (about 19
  round trips in 38 years). Too few trades to trust; do not move to it on this evidence.

## Data used

| Asset | Signal | Returns | Window |
|---|---|---|---|
| Gold | `GC=F` (as live) | `GLD` + 0.40%/yr fee add-back | 2005–2026 |
| S&P 500 | `^GSPC` (as live) | `^SP500TR` | 1988–2026 |
| MSCI World | `^990100-USD-STRD` (MSCI World index, USD) | same + assumed 2%/yr dividend | 1972–2026 |

The MSCI World index series on Yahoo (`^990100-USD-STRD`) is daily back to 1972 and is the actual index,
not an ETF proxy. It is a candidate for the live World signal instead of `SWDA.L` (GBp), pending the
owner's decision.

## Not yet tested

- Realized-volatility layer (1x/2x by volatility), from the handover's proposed architecture.
- Out-of-sample or walk-forward validation, taxes, EUR financing rates, and product-specific tracking.
