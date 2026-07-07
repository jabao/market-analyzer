# Market Analyzer

A Python project that analyzes market data to make real-time stock suggestions.
The core capability is an **interactive dashboard** that ranks S&P 500 stocks by a
**composite valuation score** (blending valuation, profitability, growth, and financial
health), powered by internal ranking/scoring functions.

## Status

| Feature | State |
| --- | --- |
| Internal function: rank S&P 500 stocks by PE ratio | ✅ Done |
| Composite scoring model (multi-metric, weighted) | ✅ Done |
| Dashboard: ranked table with valuation metrics | ✅ Done |
| Dashboard: 10 / 20 / 50 rows per page + pagination | ✅ Done |
| Dashboard: click any column header to sort asc/desc | ✅ Done |
| Dashboard: adjustable composite-score weights (sidebar sliders) | ✅ Done |
| Dashboard: click a row OR search any ticker for a full metric breakdown | ✅ Done |
| Dashboard: price history chart (1D/1W/1M/6M/1Y/5Y/MAX) in the details view | ✅ Done |
| Persistence & historical tracking | 🔜 Planned |

## Architecture

Layered so data access, ranking logic, the in-process service API, and the UI stay
independent and testable. There is **no HTTP API** — ranking is an internal function
call; the only web surface is the dashboard itself.

```
app/
  data_source.py   # Resolves the S&P 500 universe + fetches quotes (price, PE,
                   # forward PE, PEG, P/B, div yield, beta, market cap, sector) from
                   # Yahoo Finance via yfinance. Caches symbols on disk and quotes
                   # in memory (15-min TTL).
  ranking.py       # Pure functions that order quotes by a single metric (PE).
                   # No I/O, so it is fast and trivial to unit test.
  scoring.py       # Pure composite scoring model: blends valuation, profitability,
                   # growth, and financial-health metrics into a 0-100 score via
                   # percentile ranking, with adjustable dimension weights.
  service.py       # The internal API: get_scored_stocks_dataframe() / build_scored_dataframe()
                   # for the composite-ranked table, get_ranked_stocks_dataframe() for the
                   # simple PE ranking, and get_stock_details() for the full grouped metric
                   # breakdown of a single ticker.
dashboard.py       # Streamlit + AgGrid dashboard (the UI entry point).
tests/
  test_ranking.py  # Unit tests for ranking logic (no network).
  test_service.py  # Unit tests for the service layer (data source stubbed).
requirements.txt   # Runtime + dev dependencies.
```

### Data flow

1. `dashboard.py` calls `service.get_ranked_stocks_dataframe()` (cached 15 min).
2. `data_source.get_sp500_symbols()` returns the ticker universe (scraped from
   Wikipedia and cached to `.cache/`; falls back to a bundled list if offline).
3. `data_source.get_quotes()` fetches each stock's snapshot concurrently, caching
   each quote for 15 minutes to keep the UI responsive and avoid rate limits.
4. `ranking.rank_by_pe()` filters to stocks with a valid positive PE and sorts them.
5. `service` shapes the result into a DataFrame with readable column names.
6. AgGrid renders it with client-side sorting and pagination over the full dataset.

### The internal ranking / scoring functions

```python
from app.service import (
    get_ranked_stocks,             # list[Quote], simple PE ranking
    get_ranked_stocks_dataframe,   # DataFrame, simple PE ranking
    get_scored_stocks_dataframe,   # DataFrame, composite-score ranking
    get_stock_details,             # full grouped metrics for one ticker
)

# Simple PE ranking (lowest PE first)
df_pe = get_ranked_stocks_dataframe(limit=50)

# Composite ranking with custom weights (higher score = better)
df = get_scored_stocks_dataframe({
    "valuation": 40, "profitability": 30, "growth": 20, "financial_health": 10,
})
```

### Composite scoring model

Ranking on a single metric like PE can be misleading (a low PE may signal a bargain
*or* a company whose earnings are expected to collapse — a "value trap"). The composite
model blends several metrics into one 0-100 score so the ranking reflects multiple
dimensions at once:

| Dimension | Metrics (direction) | Default weight |
| --- | --- | --- |
| Valuation | trailing P/E, forward P/E, PEG, P/B (lower is better) | 40% |
| Profitability | profit margin, return on equity (higher is better) | 30% |
| Growth | revenue growth, earnings growth (higher is better) | 20% |
| Financial health | free cash flow (higher), debt/equity (lower) | 10% |

How it works (`app/scoring.py`):

1. **Normalize** each metric to a **percentile rank** within the S&P 500 (0-100), so
   metrics on different scales are comparable and outliers don't dominate. Metrics are
   oriented so higher always means "better".
2. **Average** the metric percentiles within each dimension to get a dimension sub-score.
3. **Combine** the dimension sub-scores using the (normalized) weights into the final
   composite. If a stock is missing a whole dimension, its weight is redistributed across
   the dimensions that do have data.

Non-positive valuation metrics (e.g. a negative PE from negative earnings) are treated as
missing rather than "cheap", so loss-making stocks aren't wrongly ranked as bargains. The
weights are adjustable live in the dashboard — shifting them toward Growth surfaces names
like NVDA/MSFT, while shifting toward Valuation surfaces cheaper names like JPM/XOM.

### Data source

[yfinance](https://pypi.org/project/yfinance/) (Yahoo Finance) — free, no API key
required. Isolated in `data_source.py`, so swapping in Alpaca, Finnhub, or FMP later
touches only that one module.

## Setup

```bash
uv venv --python 3.12
uv pip install -r requirements.txt
```

## Run the dashboard

```bash
uv run streamlit run dashboard.py
```

Streamlit opens it in your browser (default http://localhost:8501).

### Dashboard columns

Ticker, Company, **Score** (composite), Valuation, Profitability, Growth, Health (the
four dimension sub-scores), Sector, Price, Trailing P/E, Forward P/E, PEG, P/B,
Div Yield %, Beta, Market Cap. Rows are sorted by composite Score (best first) by default.

### Dashboard interactions

- **Adjust weights:** sidebar sliders set the relative importance of each scoring
  dimension; the table re-ranks instantly (no refetch — scoring runs on cached data).
- **Sort:** click any column header to sort ascending, click again for descending.
  Sorting applies across the whole dataset, not just the current page.
- **Page size:** choose 10, 20, or 50 rows per page (sidebar selector, or the grid's
  own page-size control).
- **Paginate:** use the pager at the bottom of the grid.
- **Refresh:** the sidebar "Refresh data" button clears the 15-min cache and refetches.
- **Stock details:** click any row **or type a ticker in the search box** to open a full
  metric breakdown below the grid — grouped into Company, Valuation, Price, Profitability
  & Growth, Financials, Dividends, and Trading, plus the business summary. The search
  works for any ticker, not just S&P 500 members; a non-empty search takes priority over
  the clicked row.
- **Price chart:** the details view opens with an interactive closing-price line chart and
  a range selector — **1D / 1W / 1M / 6M / 1Y / 5Y / MAX** (intraday granularity for short
  ranges, down to monthly for MAX).

## Testing

```bash
uv run pytest
```

## Notes

- The **first** load warms the cache by fetching the full S&P 500, so it takes a while.
  Subsequent loads within the 15-minute TTL are fast.
