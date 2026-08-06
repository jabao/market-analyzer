"""Service layer for portfolio management: live prices and gain/loss calculations."""

from __future__ import annotations

from datetime import date
import time

import yfinance as yf

from app.portfolio_db import (
    add_linked_account,
    add_transaction,
    get_aggregated_holdings,
    get_all_transactions,
    get_linked_accounts,
    get_ticker_transactions,
    init_database,
    delete_transaction,
    remove_linked_account,
    replace_imported_transactions,
    update_linked_account_refresh,
    update_purchase_date_for_ticker,
)
from app.plaid_integration import PLAID_SOURCE, PlaidPortfolioImport

_PRICE_CACHE: dict[str, tuple[float, float | None]] = {}
_PRICE_TTL_SECONDS = 30


def ensure_db_initialized() -> None:
    """Ensure the portfolio database is initialized."""
    init_database()


def add_portfolio_holding(
    ticker: str,
    shares: float,
    purchase_date: date,
    purchase_price: float,
    brokerage: str | None = None,
) -> int:
    """Add a holding/transaction to the portfolio. Returns the new record ID.
    
    Same tickers are automatically aggregated with weighted average price.
    Ticker is used as display name (stock_name removed for simplicity)."""
    return add_transaction(ticker, shares, purchase_date, purchase_price, brokerage)


def import_plaid_portfolio(import_result: PlaidPortfolioImport, brokerage: str) -> int:
    """Replace existing Plaid-imported brokerage rows with freshly imported holdings."""
    return replace_imported_transactions(
        import_result.transactions,
        source=PLAID_SOURCE,
        brokerage=brokerage,
    )


def link_brokerage_account(
    institution_name: str,
    institution_id: str | None,
    item_id: str,
    access_token: str,
    logo: str | None = None,
    cash_balance: float = 0.0,
    total_assets: float = 0.0,
) -> int:
    """Persist a newly linked brokerage account."""
    return add_linked_account(
        institution_name, institution_id, item_id, access_token,
        logo=logo, cash_balance=cash_balance, total_assets=total_assets,
    )


def get_all_linked_accounts() -> list[dict]:
    """Return all linked brokerage accounts."""
    return get_linked_accounts()


def unlink_brokerage_account(item_id: str) -> bool:
    """Remove a linked account and all its imported holdings."""
    return remove_linked_account(item_id)


def mark_account_refreshed(
    item_id: str,
    cash_balance: float = 0.0,
    total_assets: float = 0.0,
) -> None:
    """Update balances and last refresh timestamp for a linked account."""
    update_linked_account_refresh(item_id, cash_balance=cash_balance, total_assets=total_assets)


def update_holding_purchase_date(ticker: str, purchase_date_text: str) -> int:
    """Persist an edited purchase date from the holdings grid."""
    return update_purchase_date_for_ticker(ticker, purchase_date_text)


def get_portfolio_holdings() -> list[dict]:
    """Get all holdings aggregated by ticker.
    
    Returns consolidated positions with weighted average price and multiple dates."""
    return get_aggregated_holdings()


def delete_portfolio_holding(holding_id: int) -> bool:
    """Delete a transaction by ID. Returns True if successful."""
    return delete_transaction(holding_id)


def delete_all_transactions_for_ticker(ticker: str) -> bool:
    """Delete all transactions for a specific ticker. Returns True if any deleted."""
    from app.portfolio_db import get_connection, DB_PATH
    
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM transactions WHERE ticker = ?", (ticker.upper(),))
            affected = cursor.rowcount
            conn.commit()
            return affected > 0
    except Exception:
        return False


def get_ticker_positions(symbol: str) -> list[dict]:
    """Get individual transaction breakdown for a ticker."""
    return get_ticker_transactions(symbol)


def get_current_price(symbol: str, use_cache: bool = True) -> float | None:
    """Fetch current price for a symbol using yfinance."""
    now = time.time()

    if use_cache:
        cached = _PRICE_CACHE.get(symbol)
        if cached and now - cached[0] < _PRICE_TTL_SECONDS:
            return cached[1]

    try:
        ticker = yf.Ticker(symbol)
        info = ticker.info
        price = info.get("currentPrice") or info.get("regularMarketPrice")
        _PRICE_CACHE[symbol] = (now, price)
        return price
    except Exception:
        _PRICE_CACHE[symbol] = (now, None)
        return None


def get_current_prices_batch(symbols: list[str]) -> dict[str, float | None]:
    """Fetch current prices for multiple symbols concurrently."""
    results = {}
    for symbol in symbols:
        results[symbol] = get_current_price(symbol)
    return results


def clear_price_cache() -> None:
    """Clear the price cache to force fresh prices on next fetch."""
    _PRICE_CACHE.clear()


def calculate_portfolio_summary(holdings: list[dict], prices: dict[str, float | None]) -> dict:
    """Calculate portfolio totals and build a summary DataFrame with gain/loss metrics.
    
    Holdings should come from get_aggregated_holdings()."""
    total_cost_basis = 0.0
    total_current_value = 0.0

    rows = []
    for holding in holdings:
        ticker = holding["ticker"]
        total_shares = holding["total_shares"]
        avg_purchase_price = holding["avg_purchase_price"]
        current_price = prices.get(ticker)
        
        if avg_purchase_price is None:
            avg_purchase_price = 0

        cost_basis = total_shares * avg_purchase_price
        current_value = total_shares * current_price if current_price else None
        gain_loss = current_value - cost_basis if current_value else None
        gain_loss_pct = ((current_price - avg_purchase_price) / avg_purchase_price * 100) if current_price and avg_purchase_price else None

        if current_value is not None:
            total_cost_basis += cost_basis
            total_current_value += current_value

        # Assign a synthetic id for row selection (use hash of ticker)
        synthetic_id = hash(ticker) % 100000
        
        rows.append({
            "id": synthetic_id,
            "ticker_key": ticker,
            "Ticker": ticker,
            "Stock Name": holding["stock_name"],
            "Shares": total_shares,
            "Avg Purchase Price": avg_purchase_price,
            "Current Price": current_price,
            "Cost Basis": cost_basis,
            "Current Value": current_value,
            "Gain/Loss": gain_loss,
            "Gain/Loss %": gain_loss_pct,
            "Brokerage": holding.get("brokerage") or "",
        })

    total_gain_loss = total_current_value - total_cost_basis
    total_gain_loss_pct = (total_gain_loss / total_cost_basis * 100) if total_cost_basis > 0 else 0

    return {
        "rows": rows,
        "total_cost_basis": total_cost_basis,
        "total_current_value": total_current_value,
        "total_gain_loss": total_gain_loss,
        "total_gain_loss_pct": total_gain_loss_pct,
    }
