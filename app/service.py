"""Service layer: the internal API for the rest of the app. Ties together the data
source and ranking logic into simple in-process function calls (no HTTP)."""

from __future__ import annotations

import pandas as pd

from app import data_source, scoring
from app.data_source import Quote
from app.ranking import rank_by_pe

PRICE_RANGES: dict[str, tuple[str, str]] = {
    "1D": ("1d", "5m"),
    "1W": ("5d", "30m"),
    "1M": ("1mo", "1d"),
    "6M": ("6mo", "1d"),
    "1Y": ("1y", "1d"),
    "5Y": ("5y", "1wk"),
    "MAX": ("max", "1mo"),
}
DEFAULT_PRICE_RANGE = "6M"

SCORED_COLUMNS: list[str] = [
    "Ticker", "Company", "Score", "Valuation", "Profitability", "Growth", "Health",
    "Sector", "Price", "Trailing P/E", "Forward P/E", "PEG", "P/B", "Div Yield %",
    "Beta", "Market Cap",
]

DETAIL_SECTIONS: list[tuple[str, list[tuple[str, str, str]]]] = [
    ("Company", [
        ("Name", "shortName", "text"),
        ("Sector", "sector", "text"),
        ("Industry", "industry", "text"),
        ("Country", "country", "text"),
        ("Employees", "fullTimeEmployees", "int"),
        ("Website", "website", "url"),
    ]),
    ("Valuation", [
        ("Trailing P/E", "trailingPE", "ratio"),
        ("Forward P/E", "forwardPE", "ratio"),
        ("PEG", "trailingPegRatio", "ratio"),
        ("Price / Book", "priceToBook", "ratio"),
        ("Price / Sales", "priceToSalesTrailing12Months", "ratio"),
        ("EV / EBITDA", "enterpriseToEbitda", "ratio"),
        ("Market Cap", "marketCap", "large"),
        ("Enterprise Value", "enterpriseValue", "large"),
    ]),
    ("Price", [
        ("Current Price", "currentPrice", "price"),
        ("Previous Close", "previousClose", "price"),
        ("Day Low", "dayLow", "price"),
        ("Day High", "dayHigh", "price"),
        ("52-Week Low", "fiftyTwoWeekLow", "price"),
        ("52-Week High", "fiftyTwoWeekHigh", "price"),
        ("50-Day Avg", "fiftyDayAverage", "price"),
        ("200-Day Avg", "twoHundredDayAverage", "price"),
    ]),
    ("Profitability & Growth", [
        ("Profit Margin", "profitMargins", "percent"),
        ("Operating Margin", "operatingMargins", "percent"),
        ("Return on Equity", "returnOnEquity", "percent"),
        ("Return on Assets", "returnOnAssets", "percent"),
        ("Revenue Growth", "revenueGrowth", "percent"),
        ("Earnings Growth", "earningsGrowth", "percent"),
    ]),
    ("Financials", [
        ("Revenue (TTM)", "totalRevenue", "large"),
        ("Gross Profits", "grossProfits", "large"),
        ("EBITDA", "ebitda", "large"),
        ("Free Cash Flow", "freeCashflow", "large"),
        ("Total Cash", "totalCash", "large"),
        ("Total Debt", "totalDebt", "large"),
        ("Trailing EPS", "trailingEps", "price"),
        ("Forward EPS", "forwardEps", "price"),
    ]),
    ("Dividends", [
        ("Dividend Yield %", "dividendYield", "ratio"),
        ("Dividend Rate", "dividendRate", "price"),
        ("Payout Ratio", "payoutRatio", "percent"),
    ]),
    ("Trading", [
        ("Beta", "beta", "ratio"),
        ("Volume", "volume", "int"),
        ("Avg Volume", "averageVolume", "int"),
        ("Shares Outstanding", "sharesOutstanding", "count"),
    ]),
]

DISPLAY_COLUMNS: dict[str, str] = {
    "symbol": "Ticker",
    "name": "Company",
    "sector": "Sector",
    "price": "Price",
    "trailing_pe": "Trailing P/E",
    "forward_pe": "Forward P/E",
    "peg_ratio": "PEG",
    "price_to_book": "P/B",
    "dividend_yield": "Div Yield %",
    "beta": "Beta",
    "market_cap": "Market Cap",
}


def get_ranked_stocks(limit: int | None = None, ascending: bool = True) -> list[Quote]:
    """Return S&P 500 stocks ranked by trailing PE ratio (lowest first by default).

    This is the primary internal entry point: it resolves the universe, fetches quotes,
    and applies the ranking. `limit=None` returns the full ranked list."""
    symbols = data_source.get_sp500_symbols()
    quotes = data_source.get_quotes(symbols)
    return rank_by_pe(quotes, limit=limit if limit is not None else len(quotes), ascending=ascending)


def get_ranked_stocks_dataframe(limit: int | None = None, ascending: bool = True) -> pd.DataFrame:
    """Return the PE-ranked stocks as a DataFrame with human-readable column names.

    Rows are ordered by the ranking; the dividend yield is normalized to a percentage.
    Intended for direct consumption by the dashboard UI."""
    quotes = get_ranked_stocks(limit=limit, ascending=ascending)
    frame = pd.DataFrame(data_source.quote_to_dict(q) for q in quotes)
    if frame.empty:
        return pd.DataFrame(columns=list(DISPLAY_COLUMNS.values()))

    frame = frame[list(DISPLAY_COLUMNS.keys())].rename(columns=DISPLAY_COLUMNS)
    return frame


def get_quotes_dataframe() -> pd.DataFrame:
    """Fetch the S&P 500 universe as a raw DataFrame of all Quote fields (one row per
    stock). This is the network-bound step; scoring on top of it is cheap and repeatable
    as weights change."""
    symbols = data_source.get_sp500_symbols()
    quotes = data_source.get_quotes(symbols)
    return pd.DataFrame(data_source.quote_to_dict(q) for q in quotes)


def build_scored_dataframe(base_frame: pd.DataFrame, weights: dict[str, float] | None = None) -> pd.DataFrame:
    """Apply the composite scoring model to a raw quotes DataFrame and return a
    display-ready table sorted by composite score (best first)."""
    if base_frame is None or base_frame.empty:
        return pd.DataFrame(columns=SCORED_COLUMNS)

    scores = scoring.score_metrics_frame(base_frame, weights)
    merged = base_frame.merge(scores, on="symbol", how="left")
    merged = merged[merged["composite"].notna()].copy()
    if merged.empty:
        return pd.DataFrame(columns=SCORED_COLUMNS)

    merged.sort_values("composite", ascending=False, inplace=True)
    out = pd.DataFrame({
        "Ticker": merged["symbol"],
        "Company": merged["name"],
        "Score": merged["composite"],
        "Valuation": merged["valuation"],
        "Profitability": merged["profitability"],
        "Growth": merged["growth"],
        "Health": merged["financial_health"],
        "Sector": merged["sector"],
        "Price": merged["price"],
        "Trailing P/E": merged["trailing_pe"],
        "Forward P/E": merged["forward_pe"],
        "PEG": merged["peg_ratio"],
        "P/B": merged["price_to_book"],
        "Div Yield %": merged["dividend_yield"],
        "Beta": merged["beta"],
        "Market Cap": merged["market_cap"],
    })
    return out.reset_index(drop=True)


def get_scored_stocks_dataframe(weights: dict[str, float] | None = None) -> pd.DataFrame:
    """Fetch the S&P 500 and return it ranked by the composite score for the given
    dimension weights (one-shot convenience wrapper)."""
    return build_scored_dataframe(get_quotes_dataframe(), weights)


def get_price_history(symbol: str, range_key: str = DEFAULT_PRICE_RANGE) -> pd.DataFrame:
    """Return a two-column (Time, Price) DataFrame of a ticker's closing prices over the
    requested range key (one of PRICE_RANGES), ready for charting. Empty if unavailable."""
    period, interval = PRICE_RANGES.get(range_key, PRICE_RANGES[DEFAULT_PRICE_RANGE])
    history = data_source.get_price_history(symbol, period, interval)
    if history is None or history.empty or "Close" not in history.columns:
        return pd.DataFrame(columns=["Time", "Price"])

    frame = history.reset_index()
    time_column = "Datetime" if "Datetime" in frame.columns else "Date"
    out = pd.DataFrame({"Time": frame[time_column], "Price": frame["Close"]})
    return out.dropna(subset=["Price"]).reset_index(drop=True)


def get_stock_details(symbol: str) -> dict:
    """Return a full, grouped overview of a single ticker's metrics for the detail view.

    The result is `{"symbol", "name", "summary", "sections"}` where `sections` is a list
    of `(title, rows)` and each row is `(label, raw_value, kind)`; formatting is left to
    the caller so the values stay easy to test."""
    info = data_source.get_ticker_info(symbol)
    sections = [
        (title, [(label, info.get(key), kind) for label, key, kind in rows])
        for title, rows in DETAIL_SECTIONS
    ]
    found = any(info.get(key) for key in ("shortName", "longName", "currentPrice", "regularMarketPrice"))
    return {
        "symbol": symbol,
        "found": found,
        "name": info.get("shortName") or info.get("longName") or symbol,
        "summary": info.get("longBusinessSummary"),
        "sections": sections,
    }
