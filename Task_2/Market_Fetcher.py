"""
Timecell AI — Task 02: Live Market Data Fetch

Strategy: yfinance (Yahoo Finance) is the primary source for ALL assets.
          If any single asset fails, a dedicated fallback API is tried.

  Asset     │ Primary (yfinance)  │ Fallback API
  ──────────┼─────────────────────┼──────────────────────────
  BTC/USD   │ BTC-USD             │ CoinGecko (free, no key)
  NIFTY 50  │ ^NSEI               │ ^BSESN (Sensex, same API)
  GOLD      │ GC=F (futures)      │ SGOL ETF via yfinance

Run:
    python -m task02.market_fetcher
    python -m task02.market_fetcher --demo   # offline / mock mode
"""

from __future__ import annotations

import argparse
import logging
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Optional, Callable

import requests
import yfinance as yf



log = logging.getLogger("timecell.market")
log.setLevel(logging.DEBUG)

_handler = logging.StreamHandler(sys.stderr)
_handler.setFormatter(logging.Formatter("  %(levelname)-8s  %(message)s"))
log.addHandler(_handler)
log.propagate = False

IST = timezone(timedelta(hours=5, minutes=30))



@dataclass
class AssetPrice:
    name: str
    price: Optional[float]
    currency: str
    api: str                              # which API succeeded
    fetched_at: Optional[datetime] = None
    errors: list[str] = field(default_factory=list)   # all attempted errors
    used_fallback: bool = False

    @property
    def ok(self) -> bool:
        return self.price is not None and self.price == self.price  # also guards NaN



def _yfinance_price(symbol: str) -> float:
    """
    Fetch last_price for a yfinance symbol.
    Raises ValueError / any exception on failure — callers handle it.
    """
    ticker = yf.Ticker(symbol)
    price = ticker.fast_info.last_price
    if price is None:
        raise ValueError(f"yfinance returned None for {symbol}")
    if price != price:          # NaN
        raise ValueError(f"yfinance returned NaN for {symbol}")
    return round(float(price), 2)


def _coingecko_price(coin_id: str, vs_currency: str = "usd") -> tuple[float, datetime]:
    """
    Fetch price from CoinGecko free public API.
    Returns (price, exchange_timestamp).
    Raises on any failure.
    """
    url = "https://api.coingecko.com/api/v3/simple/price"
    params = {
        "ids": coin_id,
        "vs_currencies": vs_currency,
        "include_last_updated_at": "true",
    }
    resp = requests.get(url, params=params, timeout=10)
    resp.raise_for_status()
    data = resp.json()

    if coin_id not in data:
        raise ValueError(f"'{coin_id}' not found in CoinGecko response")
    raw = data[coin_id].get(vs_currency)
    if raw is None:
        raise ValueError(f"'{vs_currency}' price missing for {coin_id}")

    ts_epoch = data[coin_id].get("last_updated_at")
    ts = datetime.fromtimestamp(ts_epoch, tz=IST) if ts_epoch else datetime.now(tz=IST)
    return round(float(raw), 2), ts



def fetch_btc() -> AssetPrice:
    """
    Primary:  yfinance  BTC-USD
    Fallback: CoinGecko public API (free, no key)
    """
    asset = AssetPrice(name="BTC", price=None, currency="USD", api="")

    # ── Primary ──────────────────────────────
    try:
        log.debug("BTC primary → yfinance BTC-USD")
        asset.price = _yfinance_price("BTC-USD")
        asset.api = "Yahoo Finance"
        asset.fetched_at = datetime.now(tz=IST)
        log.info(f"BTC → USD {asset.price:,.2f}  [Yahoo Finance]")
        return asset
    except Exception as e:
        msg = f"yfinance BTC-USD: {type(e).__name__}: {e}"
        asset.errors.append(msg)
        log.warning(f"BTC primary failed — {msg}")

    # ── Fallback ─────────────────────────────
    try:
        log.debug("BTC fallback → CoinGecko")
        price, ts = _coingecko_price("bitcoin", "usd")
        asset.price = price
        asset.api = "CoinGecko (fallback)"
        asset.fetched_at = ts
        asset.used_fallback = True
        log.info(f"BTC → USD {asset.price:,.2f}  [CoinGecko fallback]")
    except requests.exceptions.Timeout:
        msg = "CoinGecko timed out (10s)"
        asset.errors.append(msg)
        log.error(f"BTC fallback failed — {msg}")
    except requests.exceptions.ConnectionError as e:
        msg = f"CoinGecko connection error: {e}"
        asset.errors.append(msg)
        log.error(f"BTC fallback failed — {msg}")
    except requests.exceptions.HTTPError as e:
        msg = f"CoinGecko HTTP {e.response.status_code}: {e.response.reason}"
        asset.errors.append(msg)
        log.error(f"BTC fallback failed — {msg}")
    except (ValueError, KeyError, TypeError) as e:
        msg = f"CoinGecko parse error: {e}"
        asset.errors.append(msg)
        log.error(f"BTC fallback failed — {msg}")

    return asset


def fetch_nifty() -> AssetPrice:
    """
    Primary:  yfinance  ^NSEI  (NIFTY 50)
    Fallback: yfinance  ^BSESN (BSE Sensex — same API, different symbol)
    """
    asset = AssetPrice(name="NIFTY 50", price=None, currency="INR", api="")

    # ── Primary ──────────────────────────────
    try:
        log.debug("NIFTY primary → yfinance ^NSEI")
        asset.price = _yfinance_price("^NSEI")
        asset.api = "Yahoo Finance"
        asset.fetched_at = datetime.now(tz=IST)
        log.info(f"NIFTY 50 → INR {asset.price:,.2f}  [Yahoo Finance]")
        return asset
    except Exception as e:
        msg = f"yfinance ^NSEI: {type(e).__name__}: {e}"
        asset.errors.append(msg)
        log.warning(f"NIFTY primary failed — {msg}")

    # ── Fallback: Sensex ──────────────────────
    try:
        log.debug("NIFTY fallback → yfinance ^BSESN (Sensex)")
        price = _yfinance_price("^BSESN")
        asset.price = price
        asset.name = "SENSEX"          # update name since it's a different index
        asset.api = "Yahoo Finance (^BSESN fallback)"
        asset.fetched_at = datetime.now(tz=IST)
        asset.used_fallback = True
        log.info(f"SENSEX → INR {asset.price:,.2f}  [Yahoo Finance fallback]")
    except Exception as e:
        msg = f"yfinance ^BSESN: {type(e).__name__}: {e}"
        asset.errors.append(msg)
        log.error(f"NIFTY fallback failed — {msg}")

    return asset


def fetch_gold() -> AssetPrice:
    """
    Primary:  yfinance  GC=F  (COMEX Gold Futures, USD/oz → converted to USD/g)
    Fallback: yfinance  SGOL  (Aberdeen Gold ETF — price in USD per share,
                               ~tracks gold closely, labeled clearly)
    """
    TROY_OZ_TO_GRAMS = 31.1035
    asset = AssetPrice(name="GOLD", price=None, currency="USD/g", api="")

    # ── Primary ──────────────────────────────
    try:
        log.debug("GOLD primary → yfinance GC=F (COMEX futures)")
        price_oz = _yfinance_price("GC=F")
        asset.price = round(price_oz / TROY_OZ_TO_GRAMS, 2)
        asset.api = "Yahoo Finance (GC=F futures)"
        asset.fetched_at = datetime.now(tz=IST)
        log.info(f"GOLD → USD/g {asset.price:,.2f}  (from {price_oz:,.2f}/oz)  [Yahoo Finance]")
        return asset
    except Exception as e:
        msg = f"yfinance GC=F: {type(e).__name__}: {e}"
        asset.errors.append(msg)
        log.warning(f"GOLD primary failed — {msg}")

    # ── Fallback: SGOL ETF ────────────────────
    try:
        log.debug("GOLD fallback → yfinance SGOL (gold ETF)")
        price = _yfinance_price("SGOL")
        asset.price = price
        asset.currency = "USD"           # ETF price, not per-gram
        asset.name = "GOLD (SGOL ETF)"
        asset.api = "Yahoo Finance (SGOL fallback)"
        asset.fetched_at = datetime.now(tz=IST)
        asset.used_fallback = True
        log.info(f"GOLD (SGOL ETF) → USD {asset.price:,.2f}  [Yahoo Finance fallback]")
    except Exception as e:
        msg = f"yfinance SGOL: {type(e).__name__}: {e}"
        asset.errors.append(msg)
        log.error(f"GOLD fallback failed — {msg}")

    return asset


# ─────────────────────────────────────────────────────────────
# Orchestrator
# ─────────────────────────────────────────────────────────────

def fetch_all_prices() -> list[AssetPrice]:
    """
    Runs all three fetchers independently.
    Each has its own primary + fallback.
    One total failure never crashes or blocks the others.
    """
    fetchers: list[Callable[[], AssetPrice]] = [
        fetch_btc,
        fetch_nifty,
        fetch_gold,
    ]
    results: list[AssetPrice] = []
    for fetcher in fetchers:
        try:
            results.append(fetcher())
        except Exception as exc:
            # Ultimate safety net — should never trigger but guards against bugs
            log.critical(
                f"Unexpected crash in {getattr(fetcher, '__name__', '?')}: {exc} — skipping"
            )
    return results


# ─────────────────────────────────────────────────────────────
# Mock / demo data
# ─────────────────────────────────────────────────────────────

def fetch_mock_data() -> list[AssetPrice]:
    now = datetime.now(tz=IST)
    return [
        AssetPrice("BTC",      75_874.00, "USD",   "Yahoo Finance",            now),
        AssetPrice("NIFTY 50", 23_922.20, "INR",   "Yahoo Finance",            now),
        AssetPrice("GOLD",         75.12, "USD/g",  "Yahoo Finance (GC=F futures)", now),
    ]


# ─────────────────────────────────────────────────────────────
# CLI table renderer — zero external libraries
# ─────────────────────────────────────────────────────────────

ANSI = {
    "green":   "\033[92m",
    "red":     "\033[91m",
    "yellow":  "\033[93m",
    "bold":    "\033[1m",
    "dim":     "\033[2m",
    "reset":   "\033[0m",
}

def _c(text: str, *styles: str) -> str:
    return "".join(ANSI[s] for s in styles) + text + ANSI["reset"]


def render_table(assets: list[AssetPrice]) -> None:
    now_ist = datetime.now(tz=IST).strftime("%Y-%m-%d %H:%M:%S IST")

    W_ASSET = 18
    W_PRICE = 16
    W_CURR  = 10
    W_API   = 32
    W_TS    = 14

    def sep(l, m, r):
        return f"  {l}{'─'*W_ASSET}{m}{'─'*W_PRICE}{m}{'─'*W_CURR}{m}{'─'*W_API}{m}{'─'*W_TS}{r}"

    print()
    print(_c(f"  Asset Prices — fetched at {now_ist}", "bold"))
    print()
    print(_c(sep("┌", "┬", "┐"), "dim"))
    print(_c(
        f"  │{'Asset':^{W_ASSET}}│{'Price':^{W_PRICE}}│"
        f"{'Currency':^{W_CURR}}│{'API Source':^{W_API}}│{'Timestamp':^{W_TS}}│",
        "bold"
    ))
    print(_c(sep("├", "┼", "┤"), "dim"))

    failed: list[AssetPrice] = []

    for a in assets:
        name_col = f" {a.name:<{W_ASSET - 1}}"
        curr_col = f" {a.currency:<{W_CURR - 1}}"
        api_label = f"{'⚡ ' if a.used_fallback else ''}{a.api}"
        api_col  = f" {api_label:<{W_API - 1}}"

        if a.ok:
            raw  = f"{a.price:>{W_PRICE - 1},.2f} "
            pcol = _c(raw, "green")
            ts   = a.fetched_at.strftime("%H:%M:%S IST") if a.fetched_at else "—"
            ts_col = f" {ts:<{W_TS - 1}}"
        else:
            pcol   = _c(f"{'ERROR':>{W_PRICE - 1}} ", "red")
            ts_col = f" {'—':<{W_TS - 1}}"
            failed.append(a)

        print(f"  │{name_col}│{pcol}│{curr_col}│{api_col}│{ts_col}│")

    print(_c(sep("└", "┴", "┘"), "dim"))

    # ── Legend for fallback ────────────────────
    if any(a.used_fallback for a in assets if a.ok):
        print(_c("  ⚡ = primary API failed, serving from fallback", "dim"))

    # ── INR note ──────────────────────────────
    nifty = next((a for a in assets if a.ok and a.currency == "INR"), None)
    if nifty:
        v = nifty.price
        inr_fmt = f"₹{v / 1_00_000:.2f} L" if v >= 1_00_000 else f"₹{v:,.2f}"
        print(_c(f"  {nifty.name} in Indian format: {inr_fmt}", "dim"))

    # ── Failure log ───────────────────────────
    if failed:
        print()
        print(_c("  ⚠  All sources failed for these assets:", "yellow", "bold"))
        for a in failed:
            for i, err in enumerate(a.errors):
                src = "primary " if i == 0 else "fallback"
                print(_c(f"     • {a.name} [{src}] — {err}", "red"))
        ok = sum(1 for a in assets if a.ok)
        print(_c(f"\n  {ok}/{len(assets)} assets fetched successfully.", "dim"))
    else:
        print(_c(f"\n  ✓ All {len(assets)} assets fetched successfully.", "green"))

    print()


# ─────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Timecell — Live Market Data Fetcher"
    )
    parser.add_argument(
        "--demo", action="store_true",
        help="Use mock data, no internet required"
    )
    args = parser.parse_args()

    if args.demo:
        log.info("DEMO mode — mock data, no API calls made")
        prices = fetch_mock_data()
    else:
        log.info("Fetching live prices (primary: Yahoo Finance, fallbacks ready)...")
        prices = fetch_all_prices()

    render_table(prices)

    if any(not a.ok for a in prices):
        sys.exit(1)


if __name__ == "__main__":
    main()