# Market Analyzer

A Python project that analyzes market data to make real-time stock suggestions.
The core capability is an **interactive dashboard** that ranks S&P 500 stocks by a
**composite valuation score** (blending valuation, profitability, growth, and financial
health), powered by internal ranking/scoring functions. Now includes an **LLM-powered
AI Assistant** for deep-dive market analysis using Claude or ChatGPT.

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
| LLM Assistant: Market Segment / Sector Recommendation mode | ✅ Done |
| LLM Assistant: Deep Dive Stock Picks with pro/con analysis | ✅ Done |
| LLM Assistant: Supports Claude (Anthropic) and ChatGPT (OpenAI) | ✅ Done |
| LLM Assistant: Prebuilt expert prompts + live market context injection | ✅ Done |
| LLM Assistant: Streaming responses + markdown export | ✅ Done |
| Portfolio tracker: manual holdings + Robinhood import via Plaid | ✅ Done |
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
  portfolio_db.py  # SQLite persistence for manual transactions and imported holdings.
  portfolio_service.py  # Portfolio aggregation, live prices, gain/loss, import helpers.
  plaid_integration.py  # Plaid Link token creation, token exchange, holdings fetch,
                        # and Robinhood holdings-to-portfolio mapping.
  plaid_link_component.py
  plaid_link_frontend/  # Minimal Streamlit custom component for Plaid Link.
  service.py       # The internal API: get_scored_stocks_dataframe() / build_scored_dataframe()
                   # for the composite-ranked table, get_ranked_stocks_dataframe() for the
                   # simple PE ranking, and get_stock_details() for the full grouped metric
                   # breakdown of a single ticker.
  llm/
    __init__.py    # Public exports: MarketAssistant, Input types, ProviderType
    providers.py   # LLM abstraction: ClaudeProvider, OpenAIProvider, model registry
    prompts.py     # Prebuilt expert prompts for sector + stock modes
    context.py     # Builds live market context strings from S&P 500 data
    assistant.py   # Orchestrator: ties context + prompts + provider -> analysis
tests/
  test_ranking.py       # Unit tests for ranking logic (no network).
  test_service.py       # Unit tests for the service layer (data source stubbed).
  test_scoring.py       # Tests for composite scoring.
  test_llm_assistant.py  # Tests for LLM prompts, providers, context, assistant (mocked)
requirements.txt   # Runtime + dev dependencies (now includes anthropic, openai, plaid-python).
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
## Robinhood Import Via Plaid

The Portfolio Tracker can import current Robinhood investment holdings through Plaid
Link. Configure Plaid credentials via environment variables:

```bash
export PLAID_CLIENT_ID=...
export PLAID_SECRET=...
export PLAID_ENV=sandbox  # sandbox, development, or production
# Optional if your network requires a custom certificate bundle:
export PLAID_CA_BUNDLE=/path/to/ca-bundle.pem
# Optional if Plaid calls are slow on your network:
export PLAID_CONNECT_TIMEOUT_SECONDS=10
export PLAID_READ_TIMEOUT_SECONDS=30
```

Then open **Portfolio Tracker → Import From Robinhood → Start Robinhood Login**.
Imported Plaid rows are stored in the SQLite portfolio database with `source='plaid'`.
Each new Robinhood import replaces previous Plaid-imported Robinhood rows and leaves
manual holdings untouched.

Plaid provides current positions rather than tax lots, so the app derives average
purchase price from Plaid cost basis when available and uses the import date as the
position date.

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

## LLM Assistant (NEW) — AI Market Deep Dive

A separate page (sidebar navigation **AI Deep Dive**) provides LLM-powered analysis with two modes:

### 1. Market Segment / Sector Recommendation
**Goal:** Recommend best market segments to invest in given current trends, news + quantitative snapshot. LLM does own sentiment and valuation inference.

**Inputs (user-provided):**
- Trends (e.g., AI CapEx, GLP-1, reshoring)
- News (Fed policy, earnings, geopolitics)
- Risk Tolerance, Time Horizon, Investment Style, Additional Preferences

**Quantitative context auto-injected (fixed top 20, no weight tweaking):**
- Top 20 ranked stocks
- Sector summary: avg score, avg valuation, count, top tickers per sector
- Broad market stats: avg P/E, score distribution, sector representation

**Output structure (institutional quality, markdown):**
- Executive Summary
- Macro & Market Regime Context (links qualitative + quantitative)
- Ranked Top 5 Sectors table + deep dive on top 3 (thesis, catalysts, valuation check, quant support, risks, exposure)
- Sectors to Avoid
- Risks & Hedges
- Action Plan (allocation %, triggers)
- Disclaimer (not financial advice)

### 2. Deep Dive Stock Picks with Pro/Con
**Goal:** Select best stock picks with balanced pro/con analysis.

**Inputs:**
- Tickers (multiselect from S&P 500 + free text, or auto-pick top ranked if blank)
- Investment thesis, trends/news, must-have/must-avoid filters
- Focus sector, risk tolerance, benchmark, num picks

**Quantitative context auto-injected:**
- Top 20 ranked snapshot (fixed)
- Per-ticker fundamentals (Company, Valuation, Price, Profitability & Growth, Financials, Dividends, Trading)
- Sector context, valuation percentiles

**Output per ticker:**
- One-liner + metrics table vs sector/S&P
- Moat analysis (Porter)
- Financial health, valuation, catalysts, Pros/Bull (3-5 bullets), Cons/Bear & Risks (3-5 bullets), Conviction & Fit
- Final comparative ranking table + portfolio construction guidance

### LLM Provider Support
- **Claude 4.8:** `claude-opus-4-20250514` (fixed, displayed as Claude 4.8)
- **GPT 5.5:** `gpt-5` (fixed, displayed as GPT 5.5)
- Switch via UI radio between Claude 4.8 / GPT 5.5 (no model selection, temp, max tokens - fixed internally)
- API key resolution: Environment variables `ANTHROPIC_API_KEY` / `OPENAI_API_KEY`
- Streaming support: toggle live token streaming for better UX
- Export: Download result as Markdown
- Prompt transparency: Expander shows full system prompt + user template

### Prebuilt Custom Prompts (in `app/llm/prompts.py`)
- `SECTOR_SYSTEM_PROMPT`: Senior strategist persona, sector rotation theory, macro-to-micro, requires balanced upside/downside
- `STOCK_SYSTEM_PROMPT`: Senior equity research analyst persona, fundamental + moat + DCF sanity, requires pro/con + conviction levels
- Templates engineered with chain-of-thought guidance, structured markdown, data-grounding instructions, disclaimer requirement

### Architecture
```
User UI (React frontend)
  -> MarketAssistant (assistant.py)
     -> build_full_context() (context.py): live S&P 500 + fundamentals -> strings
     -> build_sector/stock_prompt() (prompts.py): system+user prompts with injected context
     -> LLMProvider (providers.py): ClaudeProvider or OpenAIProvider -> generate/stream
  -> Result markdown rendered + download
```

### Setup for LLM Assistant
1. Install deps: `pip install -r requirements.txt` (now includes anthropic, openai)
2. Get API key:
   - Claude: https://console.anthropic.com
   - OpenAI: https://platform.openai.com/api-keys
3. Provide key via environment variables:
   ```bash
   export ANTHROPIC_API_KEY=sk-ant-...
   export OPENAI_API_KEY=sk-...
   ```
4. Run the backend and frontend servers
5. Choose provider/model, fill qualitative inputs, click Generate

### Cost note
LLM calls cost money per token. Context includes ~top 20 stocks + sector summary + fundamentals for selected tickers, ~2k-4k input tokens. Use Haiku / GPT-4o-mini for cheapest experimentation.

## Notes

- The **first** load warms the cache by fetching the full S&P 500, so it takes a while.
  Subsequent loads within the 15-minute TTL are fast.
- LLM analysis is for education only, not financial advice. Outputs may hallucinate — verify metrics against detail view.
