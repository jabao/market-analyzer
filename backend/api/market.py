"""Market data API endpoints.

Provides S&P 500 quotes, composite scoring, universal stock search, stock
details, and price history.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app import data_source
from app.service import (
    DEFAULT_PRICE_RANGE,
    PRICE_RANGES,
    build_scored_dataframe,
    get_price_history,
    get_quotes_dataframe,
    get_stock_details,
)
from backend.models.market import (
    PriceHistoryPoint,
    RefreshResponse,
    ScoredStocksRequest,
    StockDetailsResponse,
    StockSearchResult,
    WeightsRequest,
)

router = APIRouter()


@router.get("/quotes")
async def get_quotes() -> list[dict[str, Any]]:
    """Get raw S&P 500 quotes as a list of dictionaries."""
    try:
        df = get_quotes_dataframe()
        return df.to_dict(orient="records")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch quotes: {str(e)}")


@router.post("/scored")
async def get_scored_stocks(request: ScoredStocksRequest) -> list[dict[str, Any]]:
    """Get S&P 500 stocks ranked by composite score with custom weights."""
    try:
        quotes_df = get_quotes_dataframe()
        weights = None
        if request.weights:
            weights = {
                "valuation": request.weights.valuation,
                "profitability": request.weights.profitability,
                "growth": request.weights.growth,
                "financial_health": request.weights.financial_health,
            }
        scored_df = build_scored_dataframe(quotes_df, weights)
        return scored_df.to_dict(orient="records")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to score stocks: {str(e)}")


@router.get("/search", response_model=list[StockSearchResult])
async def search_stocks(
    q: str = Query(default="", min_length=1, max_length=50),
    limit: int = Query(default=8, ge=1, le=20),
) -> list[StockSearchResult]:
    """Search all stocks by ticker or company name via Yahoo Finance."""
    try:
        results = data_source.search_symbols(q, max_results=limit)
        return [
            StockSearchResult(
                symbol=r["symbol"],
                name=r["name"],
                exchange=r.get("exchange"),
                sector=r.get("sector"),
                industry=r.get("industry"),
                quote_type=r.get("quote_type"),
            )
            for r in results
        ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to search stocks: {str(e)}")


@router.get("/stock/{symbol}", response_model=StockDetailsResponse)
async def get_stock(symbol: str) -> StockDetailsResponse:
    """Get full details for a single stock ticker."""
    try:
        details = get_stock_details(symbol.upper())
        return StockDetailsResponse(**details)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch stock details: {str(e)}")


@router.get("/stock/{symbol}/history")
async def get_stock_history(
    symbol: str,
    range_key: str = Query(default=DEFAULT_PRICE_RANGE, description="Price range key"),
) -> list[PriceHistoryPoint]:
    """Get price history for a stock."""
    if range_key not in PRICE_RANGES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid range_key. Must be one of: {', '.join(PRICE_RANGES.keys())}",
        )
    try:
        history_df = get_price_history(symbol.upper(), range_key)
        if history_df.empty:
            return []
        return [
            PriceHistoryPoint(time=str(row["Time"]), price=float(row["Price"]))
            for _, row in history_df.iterrows()
        ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch price history: {str(e)}")


@router.get("/ranges")
async def get_price_ranges() -> dict[str, Any]:
    """Get available price range options."""
    return {
        "ranges": list(PRICE_RANGES.keys()),
        "default": DEFAULT_PRICE_RANGE,
    }


@router.post("/refresh", response_model=RefreshResponse)
async def refresh_market_data() -> RefreshResponse:
    """Clear cache and force refresh of market data on next request."""
    try:
        data_source._quote_cache.clear()
        data_source._info_cache.clear()
        data_source._history_cache.clear()
        data_source._search_cache.clear()
        return RefreshResponse(status="ok", message="Market data cache cleared")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to refresh: {str(e)}")
