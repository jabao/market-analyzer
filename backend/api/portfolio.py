"""Portfolio API endpoints.

Provides holdings management, live prices, and gain/loss calculations.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.portfolio_service import (
    add_portfolio_holding,
    calculate_portfolio_summary,
    clear_price_cache,
    delete_all_transactions_for_ticker,
    delete_portfolio_holding,
    get_current_prices_batch,
    get_portfolio_holdings,
    get_ticker_positions,
)
from backend.models.portfolio import (
    AddHoldingRequest,
    DeleteResponse,
    HoldingResponse,
    PortfolioSummaryResponse,
    TransactionResponse,
)

router = APIRouter()


def _row_to_holding_response(row: dict) -> HoldingResponse:
    """Convert a portfolio summary row to HoldingResponse."""
    return HoldingResponse(
        id=row["id"],
        ticker_key=row["ticker_key"],
        ticker=row["Ticker"],
        stock_name=row["Stock Name"],
        shares=row["Shares"],
        avg_purchase_price=row["Avg Purchase Price"],
        current_price=row["Current Price"],
        cost_basis=row["Cost Basis"],
        current_value=row["Current Value"],
        gain_loss=row["Gain/Loss"],
        gain_loss_pct=row["Gain/Loss %"],
        brokerage=row["Brokerage"],
    )


@router.get("/holdings", response_model=list[HoldingResponse])
async def get_holdings() -> list[HoldingResponse]:
    """Get all portfolio holdings aggregated by ticker."""
    try:
        holdings = get_portfolio_holdings()
        tickers = [h["ticker"] for h in holdings]
        prices = get_current_prices_batch(tickers) if tickers else {}
        summary = calculate_portfolio_summary(holdings, prices)
        return [_row_to_holding_response(row) for row in summary["rows"]]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch holdings: {str(e)}")


@router.get("/summary", response_model=PortfolioSummaryResponse)
async def get_summary() -> PortfolioSummaryResponse:
    """Get portfolio summary with totals and live prices."""
    try:
        from app.portfolio_service import get_all_linked_accounts

        holdings = get_portfolio_holdings()
        tickers = [h["ticker"] for h in holdings]
        prices = get_current_prices_batch(tickers) if tickers else {}

        linked_accounts = get_all_linked_accounts()
        total_cash = sum(a.get("cash_balance") or 0.0 for a in linked_accounts)

        if holdings:
            summary = calculate_portfolio_summary(holdings, prices)
            rows = summary["rows"]
            total_value = summary["total_current_value"]
            total_gain_loss = summary["total_gain_loss"]
            total_gain_pct = summary["total_gain_loss_pct"]
        else:
            rows = []
            total_value = 0.0
            total_gain_loss = 0.0
            total_gain_pct = 0.0

        total_assets = total_value + total_cash

        return PortfolioSummaryResponse(
            holdings=[_row_to_holding_response(row) for row in rows],
            total_holdings=len(holdings),
            total_assets=total_assets,
            total_cash=total_cash,
            invested_value=total_value,
            net_gain_loss=total_gain_loss,
            net_gain_loss_pct=total_gain_pct,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch summary: {str(e)}")


@router.post("/holdings", response_model=HoldingResponse)
async def add_holding(request: AddHoldingRequest) -> HoldingResponse:
    """Add a new holding/transaction to the portfolio."""
    try:
        holding_id = add_portfolio_holding(
            ticker=request.ticker.upper(),
            shares=request.shares,
            purchase_date=request.purchase_date,
            purchase_price=request.purchase_price,
            brokerage=request.brokerage,
        )
        holdings = get_portfolio_holdings()
        tickers = [h["ticker"] for h in holdings]
        prices = get_current_prices_batch(tickers) if tickers else {}
        summary = calculate_portfolio_summary(holdings, prices)

        for row in summary["rows"]:
            if row["ticker_key"] == request.ticker.upper():
                return _row_to_holding_response(row)

        raise HTTPException(status_code=404, detail="Holding not found after creation")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to add holding: {str(e)}")


@router.get("/holdings/{ticker}/transactions", response_model=list[TransactionResponse])
async def get_transactions(ticker: str) -> list[TransactionResponse]:
    """Get individual transactions for a specific ticker."""
    try:
        transactions = get_ticker_positions(ticker.upper())
        return [
            TransactionResponse(
                id=t["id"],
                date=t["purchase_date"],
                shares=t["shares"],
                price=t["purchase_price"],
                total_value=round(t["shares"] * t["purchase_price"], 2),
                brokerage=t.get("brokerage") or "",
            )
            for t in transactions
        ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch transactions: {str(e)}")


@router.delete("/holdings/{holding_id}", response_model=DeleteResponse)
async def delete_holding(holding_id: int) -> DeleteResponse:
    """Delete a single transaction by ID."""
    try:
        success = delete_portfolio_holding(holding_id)
        if success:
            clear_price_cache()
            return DeleteResponse(success=True, message="Transaction deleted")
        else:
            return DeleteResponse(success=False, message="Transaction not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete holding: {str(e)}")


@router.delete("/holdings/ticker/{ticker}", response_model=DeleteResponse)
async def delete_ticker_holdings(ticker: str) -> DeleteResponse:
    """Delete all transactions for a specific ticker."""
    try:
        success = delete_all_transactions_for_ticker(ticker.upper())
        if success:
            clear_price_cache()
            return DeleteResponse(success=True, message=f"All positions for {ticker.upper()} deleted")
        else:
            return DeleteResponse(success=False, message="No positions found for ticker")
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to delete ticker holdings: {str(e)}"
        )


@router.post("/refresh-prices", response_model=DeleteResponse)
async def refresh_prices() -> DeleteResponse:
    """Clear price cache to force fresh prices on next fetch."""
    try:
        clear_price_cache()
        return DeleteResponse(success=True, message="Price cache cleared")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to refresh prices: {str(e)}")
