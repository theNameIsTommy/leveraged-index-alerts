"""SMA200 hysteresis band research for the leveraged alert strategies.

Compares fixed % bands and ATR-style bands (k x 20-day mean absolute daily move)
around SMA200 for Gold, S&P 500 and MSCI World, trading a 2x daily-reset product
when BULL and cash when BEAR/NEUTRAL.

Run:  python research/backtest.py            (writes research/RESULTS.md)
      python research/backtest.py --refresh  (re-download Yahoo data)

Model assumptions are in ASSUMPTIONS below and repeated in RESULTS.md.
"""
from __future__ import annotations

import argparse
import json
import math
import statistics
import time
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

HERE = Path(__file__).resolve().parent
CACHE = HERE / "data"
RESULTS = HERE / "RESULTS.md"

ASSUMPTIONS = {
    "leverage": 2.0,
    "execution_lag_days": 1,  # signal at close t, trade at close t+1
    "switch_cost_pct": 0.15,  # spread + commission per switch, % of capital
    "product_fee_pct": 0.60,  # leveraged product TER, % per year
    "financing_spread_pct": 0.50,  # over T-bill on the borrowed (L-1) leg, % per year
    "cash_earns_tbill": True,
    "sma_window": 200,
    "atr_window": 20,
    "whipsaw_days": 20,  # a switch reversed within this many trading days
}

FIXED_BANDS = {
    "gold": [0, 0.5, 1, 1.5, 2, 2.5, 3, 4],
    "sp500": [0, 0.5, 1, 1.5, 2, 3],
    "world": [0, 0.5, 1, 1.5, 2, 3],
}
ATR_MULTIPLES = [0.5, 1, 1.5, 2, 3]
CURRENT_BAND = {"gold": 2.0, "sp500": 1.0, "world": 1.0}

STRESS = [
    ("1973-74 bear", date(1973, 1, 11), date(1974, 10, 3)),
    ("1987 crash", date(1987, 8, 25), date(1987, 12, 4)),
    ("Dot-com 2000-02", date(2000, 3, 24), date(2002, 10, 9)),
    ("GFC 2007-09", date(2007, 10, 9), date(2009, 3, 9)),
    ("Gold bear 2011-15", date(2011, 9, 6), date(2015, 12, 17)),
    ("Covid 2020", date(2020, 2, 19), date(2020, 3, 23)),
    ("2022 bear", date(2022, 1, 3), date(2022, 10, 12)),
]


@dataclass
class AssetSpec:
    id: str
    name: str
    signal: str  # Yahoo symbol for the SMA signal
    returns: str  # Yahoo symbol for daily returns
    extra_yield_pct: float = 0.0  # added to returns, e.g. dividends or ETF fee add-back
    note: str = ""


ASSETS = [
    AssetSpec(
        "gold", "Gold", signal="GC=F", returns="GLD", extra_yield_pct=0.40,
        note="Signal GC=F (as live). Returns GLD (physical gold, no futures rolls) + 0.40%/yr fee add-back. Window starts 2005, so no 2000-02 test.",
    ),
    AssetSpec(
        "sp500", "S&P 500", signal="^GSPC", returns="^SP500TR",
        note="Signal ^GSPC (as live). Returns ^SP500TR (dividends reinvested), available from 1988.",
    ),
    AssetSpec(
        "world", "MSCI World", signal="^990100-USD-STRD", returns="^990100-USD-STRD", extra_yield_pct=2.0,
        note="Signal and returns from the MSCI World price index in USD (1972+), plus an assumed 2.0%/yr dividend. The live alert uses SWDA.L (GBp), which only starts in 2009.",
    ),
]


# --------------------------------------------------------------------------- data

def fetch(symbol: str, refresh: bool) -> dict[date, float]:
    CACHE.mkdir(exist_ok=True)
    path = CACHE / (symbol.replace("^", "_").replace("=", "_") + ".json")
    if refresh or not path.exists():
        response = requests.get(
            f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}",
            params={"period1": 0, "period2": int(time.time()), "interval": "1d"},
            headers={"User-Agent": "leveraged-index-alerts-research/0.1"},
            timeout=60,
        )
        response.raise_for_status()
        path.write_text(response.text)
    result = json.loads(path.read_text())["chart"]["result"][0]
    if result["meta"].get("dataGranularity") != "1d":
        raise RuntimeError(f"{symbol}: Yahoo returned {result['meta'].get('dataGranularity')} bars")
    tz = ZoneInfo(result["meta"].get("exchangeTimezoneName") or "UTC")
    closes = result["indicators"]["quote"][0]["close"]
    series: dict[date, float] = {}
    for ts, close in zip(result["timestamp"], closes):
        if close is None or not math.isfinite(close) or close <= 0:
            continue
        series[datetime.fromtimestamp(ts, tz).date()] = float(close)
    today = date.today()
    series.pop(today, None)  # possibly incomplete
    return series


# ----------------------------------------------------------------------- strategy

def regimes(closes: list[float], band_pct: list[float]) -> list[int]:
    """Hysteresis regime per day: 1 BULL, -1 BEAR, 0 NEUTRAL (before first crossing / warm-up)."""
    window = ASSUMPTIONS["sma_window"]
    out = [0] * len(closes)
    running = 0.0
    state = 0
    for i, close in enumerate(closes):
        running += close
        if i >= window:
            running -= closes[i - window]
        if i < window - 1:
            continue
        distance = (close / (running / window) - 1.0) * 100.0
        band = band_pct[i]
        if distance >= band:
            state = 1
        elif distance <= -band:
            state = -1
        out[i] = state
    return out


def atr_pct(closes: list[float]) -> list[float]:
    """20-day mean absolute daily move in %, a close-only ATR proxy (MSCI history lacks highs/lows)."""
    n = ASSUMPTIONS["atr_window"]
    moves = [0.0] + [abs(closes[i] / closes[i - 1] - 1.0) * 100.0 for i in range(1, len(closes))]
    out, running = [], 0.0
    for i, move in enumerate(moves):
        running += move
        if i >= n:
            running -= moves[i - n]
        out.append(running / min(i + 1, n) if i else 0.0)
    return out


@dataclass
class Result:
    label: str
    daily: list[float]
    exposure: list[float]
    dates: list[date]
    switches: list[int] = field(default_factory=list)  # day indices where exposure changed
    cost_drag_pp: float = 0.0


def simulate(dates, asset_ret, rf, regime, *, label, leverage=None, cost=True) -> Result:
    lev = ASSUMPTIONS["leverage"] if leverage is None else leverage
    lag = ASSUMPTIONS["execution_lag_days"]
    fee = ASSUMPTIONS["product_fee_pct"] / 100 / 252
    spread = ASSUMPTIONS["financing_spread_pct"] / 100 / 252
    switch_cost = ASSUMPTIONS["switch_cost_pct"] / 100 if cost else 0.0
    daily, exposure, switches = [], [], []
    previous = 0.0
    for i in range(len(dates)):
        signal_index = i - 1 - lag  # return on day i is earned by the position held from close i-1
        held = lev if signal_index >= 0 and regime[signal_index] == 1 else 0.0
        r_cash = rf[i] if ASSUMPTIONS["cash_earns_tbill"] else 0.0
        if held:
            r = held * asset_ret[i] - (held - 1) * (rf[i] + spread) - fee
        else:
            r = r_cash
        if held != previous and i > 0:
            r -= switch_cost
            switches.append(i)
        previous = held
        daily.append(r)
        exposure.append(held)
    return Result(label, daily, exposure, dates, switches)


# ------------------------------------------------------------------------ metrics

def equity(daily):
    value, curve = 1.0, []
    for r in daily:
        value *= 1 + r
        curve.append(value)
    return curve


def max_drawdown(daily):
    peak, worst, value = 1.0, 0.0, 1.0
    for r in daily:
        value *= 1 + r
        peak = max(peak, value)
        worst = min(worst, value / peak - 1)
    return worst


def cagr(daily):
    years = len(daily) / 252
    end = equity(daily)[-1] if daily else 1.0
    return end ** (1 / years) - 1 if years > 0 and end > 0 else -1.0


def sharpe_sortino(daily, rf):
    excess = [r - f for r, f in zip(daily, rf)]
    mean = statistics.fmean(excess)
    sd = statistics.pstdev(excess)
    downside = math.sqrt(statistics.fmean([min(e, 0.0) ** 2 for e in excess]))
    return (mean / sd * math.sqrt(252) if sd else 0.0, mean / downside * math.sqrt(252) if downside else 0.0)


def trade_stats(result: Result):
    """Round trips (in -> out), whipsaws, holding period, worst losing streak."""
    trips, start = [], None
    for i, exp in enumerate(result.exposure):
        if exp and start is None:
            start = i
        elif not exp and start is not None:
            trips.append((start, i))
            start = None
    if start is not None:
        trips.append((start, len(result.exposure)))
    trip_returns = []
    for a, b in trips:
        value = 1.0
        for r in result.daily[a:b]:
            value *= 1 + r
        trip_returns.append(value - 1)
    sw = result.switches
    whipsaws = sum(1 for a, b in zip(sw, sw[1:]) if b - a <= ASSUMPTIONS["whipsaw_days"])
    streak = worst_streak = 0
    streak_loss = worst_loss = 0.0
    for tr in trip_returns:
        if tr < 0:
            streak += 1
            streak_loss = (1 + streak_loss) * (1 + tr) - 1
            if streak > worst_streak or (streak == worst_streak and streak_loss < worst_loss):
                worst_streak, worst_loss = streak, streak_loss
        else:
            streak, streak_loss = 0, 0.0
    holds = [b - a for a, b in trips]
    return {
        "trips": len(trips),
        "whipsaws": whipsaws,
        "avg_hold": statistics.fmean(holds) if holds else 0.0,
        "worst_streak": worst_streak,
        "worst_streak_loss": worst_loss,
        "win_rate": sum(tr > 0 for tr in trip_returns) / len(trip_returns) if trip_returns else 0.0,
    }


def period_return(result: Result, start: date, end: date):
    idx = [i for i, d in enumerate(result.dates) if start < d <= end]
    if not idx or result.dates[0] > start:
        return None
    seg = result.daily[idx[0]: idx[-1] + 1]
    return equity(seg)[-1] - 1, max_drawdown(seg)


def summarize(result: Result, rf, years):
    sharpe, sortino = sharpe_sortino(result.daily, rf)
    stats = trade_stats(result)
    return {
        "label": result.label,
        "cagr": cagr(result.daily),
        "maxdd": max_drawdown(result.daily),
        "sharpe": sharpe,
        "sortino": sortino,
        "switches_per_yr": len(result.switches) / years,
        "time_in": sum(1 for e in result.exposure if e) / len(result.exposure),
        "cost_drag_pp": result.cost_drag_pp,
        **stats,
    }


# -------------------------------------------------------------------------- runner

def run_asset(spec: AssetSpec, rf_series: dict[date, float], refresh: bool):
    signal = fetch(spec.signal, refresh)
    returns_px = signal if spec.returns == spec.signal else fetch(spec.returns, refresh)
    dates = sorted(set(signal) & set(returns_px))
    closes = [signal[d] for d in dates]
    px = [returns_px[d] for d in dates]
    extra = spec.extra_yield_pct / 100 / 252
    asset_ret = [0.0] + [px[i] / px[i - 1] - 1 + extra for i in range(1, len(px))]

    rf_dates = sorted(rf_series)
    rf, j, last = [], 0, rf_series[rf_dates[0]]
    for d in dates:
        while j < len(rf_dates) and rf_dates[j] <= d:
            last = rf_series[rf_dates[j]]
            j += 1
        rf.append(last / 100 / 252)

    # Evaluate from the first day with a full SMA window (+ lag).
    start = ASSUMPTIONS["sma_window"] + 1
    trimmed = lambda xs: xs[start:]  # noqa: E731
    ev_dates, ev_ret, ev_rf = trimmed(dates), trimmed(asset_ret), trimmed(rf)
    years = len(ev_dates) / 252

    atr = atr_pct(closes)
    variants: list[tuple[str, str, list[float]]] = []
    for b in FIXED_BANDS[spec.id]:
        variants.append(("fixed", f"±{b:g}%", [float(b)] * len(closes)))
    for k in ATR_MULTIPLES:
        variants.append(("atr", f"{k:g}×ATR20", [k * a for a in atr]))

    rows, results = [], {}
    always_in = [1] * len(ev_dates)
    for lev, label in [(1.0, "Buy & hold 1x"), (2.0, "Buy & hold 2x daily")]:
        res = simulate(ev_dates, ev_ret, ev_rf, always_in, label=label, leverage=lev)
        rows.append(("baseline", summarize(res, ev_rf, years)))
        results[label] = res
    for kind, label, band in variants:
        reg = trimmed(regimes(closes, band))
        res = simulate(ev_dates, ev_ret, ev_rf, reg, label=label)
        free = simulate(ev_dates, ev_ret, ev_rf, reg, label=label, cost=False)
        res.cost_drag_pp = (cagr(free.daily) - cagr(res.daily)) * 100
        rows.append((kind, summarize(res, ev_rf, years)))
        results[label] = res

    # Sub-period robustness: split the window in half.
    half = len(ev_dates) // 2
    halves = {}
    for kind, label, band in variants:
        r = results[label]
        halves[label] = tuple(
            sharpe_sortino(r.daily[a:b], ev_rf[a:b])[0] for a, b in [(0, half), (half, len(ev_dates))]
        )
    atr_now = atr[-1]
    return {
        "spec": spec,
        "start": ev_dates[0],
        "end": ev_dates[-1],
        "years": years,
        "rows": rows,
        "results": results,
        "halves": halves,
        "half_split": ev_dates[half],
        "atr_now": atr_now,
        "atr_median": statistics.median(atr[start:]),
    }


def plateau(rows, key="sharpe"):
    """Average of each fixed band's metric with its neighbours: a broad plateau scores well."""
    fixed = [r for kind, r in rows if kind == "fixed"]
    out = {}
    for i, r in enumerate(fixed):
        nbrs = fixed[max(0, i - 1): i + 2]
        out[r["label"]] = statistics.fmean(n[key] for n in nbrs)
    return out


# -------------------------------------------------------------------------- report

def pct(x, digits=1):
    return f"{x * 100:+.{digits}f}%" if x is not None else "n/a"


def render(reports) -> str:
    a = ASSUMPTIONS
    lines = [
        "# SMA200 band research",
        "",
        f"Generated {date.today().isoformat()} by `research/backtest.py`. Re-run to refresh.",
        "",
        "## Model",
        "",
        f"- BULL (close ≥ SMA200 + band) holds a {a['leverage']:g}x daily-reset product; BEAR/NEUTRAL holds cash.",
        f"- Trade {a['execution_lag_days']} day after the signal close (alerts arrive overnight).",
        f"- 2x cost: borrowed leg pays the 13-week T-bill (^IRX) + {a['financing_spread_pct']}%/yr, plus {a['product_fee_pct']}%/yr product fee.",
        f"- {a['switch_cost_pct']}% of capital per switch. Cash earns the T-bill rate. No taxes.",
        f"- ATR-style band = k × 20-day mean absolute daily move (close-only, because MSCI history lacks highs/lows).",
        f"- Whipsaw = a switch reversed within {a['whipsaw_days']} trading days. Worst streak = consecutive losing round trips.",
        "- All CAGR figures are after costs. 'Cost drag' = CAGR lost to switch costs alone.",
        "- In-sample history only. Past regimes, rates and volatility will differ.",
        "",
    ]
    for rep in reports:
        spec = rep["spec"]
        cur = f"±{CURRENT_BAND[spec.id]:g}%"
        lines += [
            f"## {spec.name}",
            "",
            f"{spec.note}",
            "",
            f"Window {rep['start']} → {rep['end']} ({rep['years']:.1f} years). Current live band: **{cur}**. "
            f"ATR20 today {rep['atr_now']:.2f}%, median {rep['atr_median']:.2f}%.",
            "",
            "| Variant | CAGR | Max DD | Sharpe | Sortino | Switches/yr | Whipsaws | Avg hold (d) | Worst losing streak | Time in | Cost drag |",
            "|---|---|---|---|---|---|---|---|---|---|---|",
        ]
        for kind, r in rep["rows"]:
            name = f"**{r['label']}** (live)" if r["label"] == cur else r["label"]
            if kind == "baseline":
                lines.append(
                    f"| {name} | {pct(r['cagr'])} | {pct(r['maxdd'], 0)} | {r['sharpe']:.2f} | {r['sortino']:.2f} | – | – | – | – | 100% | – |"
                )
                continue
            lines.append(
                f"| {name} | {pct(r['cagr'])} | {pct(r['maxdd'], 0)} | {r['sharpe']:.2f} | {r['sortino']:.2f} | "
                f"{r['switches_per_yr']:.1f} | {r['whipsaws']} | {r['avg_hold']:.0f} | "
                f"{r['worst_streak']} ({pct(r['worst_streak_loss'], 0)}) | {r['time_in'] * 100:.0f}% | {r['cost_drag_pp']:.2f} pp |"
            )
        plat = plateau(rep["rows"])
        lines += [
            "",
            f"Sharpe by half (split {rep['half_split']}) and neighbour-averaged Sharpe (plateau):",
            "",
            "| Variant | 1st half | 2nd half | Plateau |",
            "|---|---|---|---|",
        ]
        for label, (h1, h2) in rep["halves"].items():
            lines.append(f"| {label} | {h1:.2f} | {h2:.2f} | {plat.get(label, float('nan')):.2f} |".replace("nan", "–"))
        lines += ["", "Stress periods (return / max drawdown inside the period):", ""]
        show = ["Buy & hold 1x", "Buy & hold 2x daily", "±0%", cur, "1×ATR20"]
        lines.append("| Period | " + " | ".join(show) + " |")
        lines.append("|---|" + "---|" * len(show))
        for name, s, e in STRESS:
            cells = []
            for label in show:
                pr = period_return(rep["results"][label], s, e)
                cells.append("n/a" if pr is None else f"{pct(pr[0], 0)} / {pct(pr[1], 0)}")
            if all(c == "n/a" for c in cells):
                continue
            lines.append(f"| {name} | " + " | ".join(cells) + " |")
        lines.append("")
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--refresh", action="store_true")
    args = parser.parse_args()
    rf = fetch("^IRX", args.refresh)
    reports = [run_asset(spec, rf, args.refresh) for spec in ASSETS]
    RESULTS.write_text(render(reports), encoding="utf-8")
    print(f"Wrote {RESULTS}")


if __name__ == "__main__":
    main()
