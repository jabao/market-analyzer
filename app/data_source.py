"""Data-source layer: resolves the S&P 500 universe and fetches per-stock fundamentals
(price, PE ratio, market cap) from Yahoo Finance via yfinance, with on-disk and
in-memory caching so repeated API calls stay fast."""

from __future__ import annotations

import io
import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from pathlib import Path

import pandas as pd
import requests
import yfinance as yf

_HTTP_HEADERS = {"User-Agent": "market-analyzer/0.1 (https://example.com)"}

CACHE_DIR = Path(__file__).resolve().parent.parent / ".cache"
SP500_CACHE = CACHE_DIR / "sp500_symbols.json"
SP500_URL = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"

_QUOTE_TTL_SECONDS = 15 * 60
_MAX_WORKERS = 16

FALLBACK_SP500 = [
    "AAPL", "MSFT", "AMZN", "NVDA", "GOOGL", "GOOG", "META", "TSLA", "BRK-B", "JPM",
    "V", "JNJ", "WMT", "UNH", "MA", "PG", "HD", "XOM", "CVX", "LLY",
    "ABBV", "PEP", "KO", "MRK", "AVGO", "COST", "BAC", "ADBE", "CSCO", "MCD",
    "CRM", "ACN", "TMO", "ABT", "DIS", "INTC", "WFC", "VZ", "CMCSA", "PFE",
    "NKE", "TXN", "PM", "NEE", "ORCL", "AMD", "HON", "UNP", "QCOM", "IBM",
]


@dataclass
class Quote:
    """A single stock's snapshot of the metrics used for ranking and display.

    `pe_ratio` mirrors `trailing_pe` and is the field the default PE ranking sorts on."""

    symbol: str
    name: str | None
    sector: str | None
    price: float | None
    pe_ratio: float | None
    trailing_pe: float | None
    forward_pe: float | None
    peg_ratio: float | None
    price_to_book: float | None
    dividend_yield: float | None
    beta: float | None
    market_cap: float | None
    profit_margin: float | None = None
    return_on_equity: float | None = None
    revenue_growth: float | None = None
    earnings_growth: float | None = None
    debt_to_equity: float | None = None
    free_cash_flow: float | None = None


_quote_cache: dict[str, tuple[float, Quote]] = {}
_info_cache: dict[str, tuple[float, dict]] = {}
_history_cache: dict[tuple[str, str, str], tuple[float, pd.DataFrame]] = {}


def get_sp500_symbols(force_refresh: bool = False) -> list[str]:
    """Return S&P 500 ticker symbols, fetched from Wikipedia and cached on disk.

    Falls back to the on-disk cache and then a bundled static list if the network
    fetch fails, so the service always has a usable universe."""
    if not force_refresh:
        cached = _read_cached_symbols()
        if cached:
            return cached

    try:
        response = requests.get(SP500_URL, headers=_HTTP_HEADERS, timeout=15)
        response.raise_for_status()
        tables = pd.read_html(io.StringIO(response.text))
        symbols = tables[0]["Symbol"].astype(str).str.replace(".", "-", regex=False).tolist()
        symbols = [s.strip().upper() for s in symbols if s.strip()]
        if symbols:
            _write_cached_symbols(symbols)
            return symbols
    except Exception:
        pass

    cached = _read_cached_symbols()
    return cached or list(FALLBACK_SP500)


def get_quotes(symbols: list[str], use_cache: bool = True) -> list[Quote]:
    """Fetch quotes for the given symbols concurrently, returning one Quote each.

    Symbols whose data cannot be fetched are returned with None fields rather than
    dropped, so callers can decide how to filter them."""
    results: list[Quote] = []
    to_fetch: list[str] = []
    now = time.time()

    for symbol in symbols:
        if use_cache:
            entry = _quote_cache.get(symbol)
            if entry and now - entry[0] < _QUOTE_TTL_SECONDS:
                results.append(entry[1])
                continue
        to_fetch.append(symbol)

    if to_fetch:
        with ThreadPoolExecutor(max_workers=_MAX_WORKERS) as executor:
            futures = {executor.submit(_fetch_one, s): s for s in to_fetch}
            for future in as_completed(futures):
                quote = future.result()
                _quote_cache[quote.symbol] = (time.time(), quote)
                results.append(quote)

    return results


def get_ticker_info(symbol: str, use_cache: bool = True) -> dict:
    """Return the full raw yfinance `info` dict for a single ticker, cached in memory.

    Used to power the detailed single-stock view; returns an empty dict if the fetch
    fails so callers can render gracefully."""
    now = time.time()
    if use_cache:
        entry = _info_cache.get(symbol)
        if entry and now - entry[0] < _QUOTE_TTL_SECONDS:
            return entry[1]

    try:
        info = dict(yf.Ticker(symbol).info)
    except Exception:
        info = {}
    _info_cache[symbol] = (time.time(), info)
    return info


def get_price_history(symbol: str, period: str, interval: str, use_cache: bool = True) -> pd.DataFrame:
    """Return OHLCV price history for a ticker over the given yfinance period/interval,
    cached in memory. Returns an empty DataFrame if the fetch fails."""
    key = (symbol, period, interval)
    now = time.time()
    if use_cache:
        entry = _history_cache.get(key)
        if entry and now - entry[0] < _QUOTE_TTL_SECONDS:
            return entry[1]

    try:
        history = yf.Ticker(symbol).history(period=period, interval=interval)
    except Exception:
        history = pd.DataFrame()
    _history_cache[key] = (time.time(), history)
    return history


def _fetch_one(symbol: str) -> Quote:
    try:
        info = yf.Ticker(symbol).info
        trailing_pe = info.get("trailingPE")
        dividend_yield = info.get("dividendYield")
        return Quote(
            symbol=symbol,
            name=info.get("shortName") or info.get("longName"),
            sector=info.get("sector"),
            price=info.get("currentPrice") or info.get("regularMarketPrice"),
            pe_ratio=trailing_pe,
            trailing_pe=trailing_pe,
            forward_pe=info.get("forwardPE"),
            peg_ratio=info.get("trailingPegRatio") or info.get("pegRatio"),
            price_to_book=info.get("priceToBook"),
            dividend_yield=dividend_yield,
            beta=info.get("beta"),
            market_cap=info.get("marketCap"),
            profit_margin=info.get("profitMargins"),
            return_on_equity=info.get("returnOnEquity"),
            revenue_growth=info.get("revenueGrowth"),
            earnings_growth=info.get("earningsGrowth"),
            debt_to_equity=info.get("debtToEquity"),
            free_cash_flow=info.get("freeCashflow"),
        )
    except Exception:
        return _empty_quote(symbol)


def _empty_quote(symbol: str) -> Quote:
    return Quote(
        symbol=symbol,
        name=None,
        sector=None,
        price=None,
        pe_ratio=None,
        trailing_pe=None,
        forward_pe=None,
        peg_ratio=None,
        price_to_book=None,
        dividend_yield=None,
        beta=None,
        market_cap=None,
    )


def quote_to_dict(quote: Quote) -> dict:
    """Convert a Quote to a plain dict for JSON serialization."""
    return asdict(quote)


def _read_cached_symbols() -> list[str] | None:
    if SP500_CACHE.exists():
        try:
            return json.loads(SP500_CACHE.read_text())
        except Exception:
            return None
    return None


def _write_cached_symbols(symbols: list[str]) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    SP500_CACHE.write_text(json.dumps(symbols))
