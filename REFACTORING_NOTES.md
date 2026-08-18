# Market Analyzer - React + FastAPI Refactoring

## Overview

This project has been refactored from a Streamlit monolith to a modern **React frontend + FastAPI backend** architecture.

### Architecture

```
market-analyzer/
├── backend/                 # FastAPI Python backend
│   ├── main.py             # FastAPI app entry point
│   ├── api/
│   │   ├── market.py       # Market data endpoints
│   │   ├── portfolio.py    # Portfolio endpoints
│   │   ├── llm.py          # LLM assistant endpoints
│   │   └── plaid.py        # Plaid integration endpoints
│   └── models/             # Pydantic request/response models
├── frontend/                # React TypeScript frontend
│   ├── src/
│   │   ├── pages/
│   │   │   ├── MarketRankingPage.tsx
│   │   │   ├── PortfolioPage.tsx
│   │   │   └── AIAssistantPage.tsx
│   │   ├── services/
│   │   │   └── api.ts      # API client
│   │   ├── App.tsx
│   │   └── main.tsx
│   └── package.json
├── app/                     # Existing business logic (reused)
│   ├── data_source.py
│   ├── scoring.py
│   ├── service.py
│   ├── portfolio_service.py
│   └── llm/
└── requirements.txt
```

## Features Preserved

All features from the original Streamlit app are preserved:

### 1. Market Ranking Page (`/`)
- S&P 500 stocks ranked by composite valuation score
- Adjustable weights for Valuation, Profitability, Growth, Financial Health
- Sortable columns (click headers)
- Pagination (10/20/50 rows)
- Stock details view with:
  - Full metric breakdown
  - Interactive price chart (1D/1W/1M/6M/1Y/5Y/MAX)
  - Business summary

### 2. Portfolio Tracker (`/portfolio`)
- Manual holdings management
- Robinhood import via Plaid
- Live price updates (30-second auto-refresh)
- Gain/loss calculations
- Transaction history per ticker
- Linked brokerage accounts display
- Delete holdings/transactions

### 3. AI Assistant (`/ai`)
- Sector/Segment Recommendation mode
- Deep Dive Stock Picks mode
- Claude 4.8 and GPT 5.5 support
- Streaming responses
- Markdown export
- API key management

## Running the Application

### Backend (FastAPI)

```bash
# Install dependencies
uv pip install -r requirements.txt

# Run development server
uv run uvicorn backend.main:app --reload --port 8000

# Or directly
uv run python backend/main.py
```

The API will be available at:
- API: http://localhost:8000
- Docs: http://localhost:8000/docs
- Health: http://localhost:8000/health

### Frontend (React + Vite)

```bash
# Navigate to frontend
cd frontend

# Install dependencies
npm install

# Run development server
npm run dev
```

The frontend will be available at http://localhost:5173

Vite is configured to proxy `/api` requests to the backend automatically.

## API Endpoints

### Market Data
- `GET /api/market/quotes` - Get raw S&P 500 quotes
- `POST /api/market/scored` - Get scored stocks with weights
- `GET /api/market/stock/{symbol}` - Get stock details
- `GET /api/market/stock/{symbol}/history?range_key=6M` - Get price history
- `GET /api/market/ranges` - Get available price ranges
- `POST /api/market/refresh` - Clear cache

### Portfolio
- `GET /api/portfolio/holdings` - Get holdings
- `GET /api/portfolio/summary` - Get portfolio summary
- `POST /api/portfolio/holdings` - Add holding
- `GET /api/portfolio/holdings/{ticker}/transactions` - Get transactions
- `DELETE /api/portfolio/holdings/{id}` - Delete transaction
- `DELETE /api/portfolio/holdings/ticker/{ticker}` - Delete all for ticker
- `POST /api/portfolio/refresh-prices` - Clear price cache

### Plaid
- `GET /api/plaid/config` - Check configuration
- `POST /api/plaid/link-token` - Create link token
- `POST /api/plaid/exchange` - Exchange public token
- `GET /api/plaid/accounts` - Get linked accounts
- `POST /api/plaid/accounts/{item_id}/refresh` - Refresh account
- `DELETE /api/plaid/accounts/{item_id}` - Unlink account

### LLM
- `GET /api/llm/providers` - Get available providers
- `POST /api/llm/sector-analysis` - Generate sector analysis
- `POST /api/llm/stock-analysis` - Generate stock analysis

Both LLM endpoints support streaming via Server-Sent Events when `stream: true` is passed.

## Environment Variables

### Backend
```bash
# Plaid (optional, for brokerage import)
PLAID_CLIENT_ID=your_client_id
PLAID_SECRET=your_secret
PLAID_ENV=sandbox  # or development, production

# LLM API Keys (can also be passed via frontend)
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-...

# Optional Plaid timeouts
PLAID_CONNECT_TIMEOUT_SECONDS=10
PLAID_READ_TIMEOUT_SECONDS=30
PLAID_CA_BUNDLE=/path/to/ca-bundle.pem
```

## Key Improvements

1. **Separation of Concerns**: Backend handles business logic, frontend handles UI
2. **Modern UI**: React with Tailwind CSS for a clean, responsive design
3. **Type Safety**: TypeScript frontend, Pydantic models backend
4. **Better State Management**: TanStack Query for server state, React hooks for local state
5. **Improved Charts**: Recharts for interactive price charts
6. **Better Tables**: TanStack Table for sortable, paginated data grids
7. **API Documentation**: Auto-generated FastAPI docs at `/docs`
8. **Scalability**: Easy to add mobile apps or other clients that consume the API

## Migration Notes

The original `dashboard.py` (Streamlit) is preserved for reference but no longer the primary interface. All business logic in `app/` is reused by the FastAPI backend with minimal changes.

The Streamlit app can still be run with:
```bash
uv run streamlit run dashboard.py
```

But the new React app is the recommended interface going forward.
