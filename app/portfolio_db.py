"""Database module for managing user portfolio holdings using SQLite.

Stores individual transactions and aggregates by ticker for display.
Same tickers are combined with share-weighted average purchase price.
Supports multiple purchase dates displayed as "(date (shares), ...)"."""

from __future__ import annotations

import sqlite3
from datetime import date
from pathlib import Path

DATABASE_PATH = Path(__file__).resolve().parent.parent / "portfolio.db"


def get_connection() -> sqlite3.Connection:
    """Return a connection to the portfolio database, creating it if needed."""
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    return conn


# Export for external access if needed
DB_PATH = DATABASE_PATH


def init_database() -> None:
    """Initialize the database schema, creating tables if they don't exist."""
    with get_connection() as conn:
        cursor = conn.cursor()
        # Transactions table stores individual purchases (stock_name removed entirely)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticker TEXT NOT NULL,
                shares REAL NOT NULL,
                purchase_date DATE NOT NULL,
                purchase_price REAL NOT NULL,
                brokerage TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()


def add_transaction(
    ticker: str,
    shares: float,
    purchase_date: date,
    purchase_price: float,
    brokerage: str | None = None,
) -> int:
    """Add a new transaction to the portfolio. Returns the new record ID."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO transactions (ticker, shares, purchase_date, purchase_price, brokerage)
            VALUES (?, ?, ?, ?, ?)
            """,
            (ticker.upper(), shares, str(purchase_date), purchase_price, brokerage),
        )
        conn.commit()
        return cursor.lastrowid


def get_all_transactions() -> list[dict]:
    """Retrieve all transactions from the portfolio."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM transactions ORDER BY ticker, purchase_date")
        rows = cursor.fetchall()
        return [dict(row) for row in rows]


def delete_transaction(transaction_id: int) -> bool:
    """Delete a transaction by its ID. Returns True if deleted, False if not found."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM transactions WHERE id = ?", (transaction_id,))
        conn.commit()
        return cursor.rowcount > 0


def get_aggregated_holdings() -> list[dict]:
    """Get all transactions aggregated by ticker.
    
    Returns consolidated holdings with:
    - Total shares (summed)
    - Weighted average purchase price
    - Multiple purchase dates formatted as "M/D/YY (shares), ..." (same dates combined)
    - Uses ticker as display name
    - Combined brokerages
    """
    with get_connection() as conn:
        cursor = conn.cursor()
        
        # First step: aggregate by date to combine same tickers on same date
        # Second step: aggregate by ticker to get final totals using original table data
        cursor.execute("""
            WITH date_agg AS (
                SELECT 
                    da.ticker,
                    da.purchase_date,
                    SUM(da.shares) as shares,
                    AVG(da.purchase_price) as purchase_price
                FROM transactions da
                GROUP BY da.ticker, da.purchase_date
            )
            SELECT 
                da.ticker,
                SUM(da.shares) as total_shares,
                SUM(da.shares * da.purchase_price) / SUM(da.shares) as avg_purchase_price,
                GROUP_CONCAT(
                    printf('%d/%d/%d', 
                        CAST(substr(da.purchase_date, 6, 2) AS INTEGER),
                        CAST(substr(da.purchase_date, 9, 2) AS INTEGER),
                        CAST(substr(da.purchase_date, 1, 4) AS INTEGER) % 100
                    ) || ' (' || CAST(da.shares AS INTEGER) || ')',
                    ', '
                ) as purchase_dates_str,
                NULL as brokerage
            FROM date_agg da
            GROUP BY da.ticker
            ORDER BY da.ticker
        """)
        
        rows = cursor.fetchall()
        results = []
        for row in rows:
            d = dict(row)
            
            # Use ticker as the stock name
            d["stock_name"] = d["ticker"]
            
            # Format average price if calculated
            if d["avg_purchase_price"]:
                d["avg_purchase_price"] = round(d["avg_purchase_price"], 2)
            
            # Create display string for brokerages (combine unique ones)
            cursor.execute("""
                SELECT DISTINCT brokerage 
                FROM transactions 
                WHERE ticker = ? AND brokerage IS NOT NULL AND brokerage != ''
            """, (d["ticker"],))
            brokerages = [r[0] for r in cursor.fetchall()]
            d["brokerage"] = ", ".join(brokerages) if len(brokerages) > 1 else (brokerages[0] if brokerages else "")
            
            results.append(d)
        
        return results


def get_ticker_transactions(ticker: str) -> list[dict]:
    """Get all transactions for a specific ticker (for detailed view)."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM transactions WHERE ticker = ? ORDER BY purchase_date",
            (ticker.upper(),)
        )
        rows = cursor.fetchall()
        return [dict(row) for row in rows]


def clear_all() -> None:
    """Clear all transactions from the database."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM transactions")
        conn.commit()
