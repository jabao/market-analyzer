"""Database module for managing user portfolio holdings using SQLite.

Stores individual transactions and aggregates by ticker for display.
Same tickers are combined with share-weighted average purchase price.
Supports multiple purchase dates displayed as "(date (shares), ...)"."""

from __future__ import annotations

import sqlite3
from datetime import date, datetime
from pathlib import Path

DATABASE_PATH = Path(__file__).resolve().parent.parent / "portfolio.db"


def get_connection() -> sqlite3.Connection:
    """Return a connection to the portfolio database, creating it if needed."""
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    return conn


# Export for external access if needed
DB_PATH = DATABASE_PATH


def _stored_purchase_date(value) -> str:
    if value is None:
        return ""
    return str(value)


def parse_purchase_date(value: str) -> str:
    """Parse a user-entered purchase date into ISO format, or empty string."""
    value = (value or "").strip()
    if not value:
        return ""

    # Users may edit the aggregate display value "7/30/26 (3.25)" directly.
    value = value.split("(", 1)[0].strip()
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y", "%m-%d-%Y", "%m-%d-%y"):
        try:
            return datetime.strptime(value, fmt).date().isoformat()
        except ValueError:
            continue
    raise ValueError("Use YYYY-MM-DD or M/D/YY.")


def _table_columns(cursor: sqlite3.Cursor, table_name: str) -> set[str]:
    cursor.execute(f"PRAGMA table_info({table_name})")
    return {row[1] for row in cursor.fetchall()}


def _ensure_column(cursor: sqlite3.Cursor, table_name: str, column_name: str, column_definition: str) -> None:
    if column_name not in _table_columns(cursor, table_name):
        cursor.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_definition}")


def init_database() -> None:
    """Initialize the database schema, creating tables if they don't exist."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticker TEXT NOT NULL,
                shares REAL NOT NULL,
                purchase_date DATE NOT NULL,
                purchase_price REAL NOT NULL,
                brokerage TEXT,
                source TEXT NOT NULL DEFAULT 'manual',
                external_item_id TEXT,
                external_account_id TEXT,
                external_security_id TEXT,
                imported_at DATETIME,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        _ensure_column(cursor, "transactions", "source", "TEXT NOT NULL DEFAULT 'manual'")
        _ensure_column(cursor, "transactions", "external_item_id", "TEXT")
        _ensure_column(cursor, "transactions", "external_account_id", "TEXT")
        _ensure_column(cursor, "transactions", "external_security_id", "TEXT")
        _ensure_column(cursor, "transactions", "imported_at", "DATETIME")

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS linked_accounts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                institution_name TEXT NOT NULL,
                institution_id TEXT,
                item_id TEXT NOT NULL UNIQUE,
                access_token TEXT NOT NULL,
                logo TEXT,
                cash_balance REAL NOT NULL DEFAULT 0,
                total_assets REAL NOT NULL DEFAULT 0,
                linked_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                last_refreshed_at DATETIME
            )
        """)
        _ensure_column(cursor, "linked_accounts", "last_refreshed_at", "DATETIME")
        _ensure_column(cursor, "linked_accounts", "cash_balance", "REAL NOT NULL DEFAULT 0")
        _ensure_column(cursor, "linked_accounts", "total_assets", "REAL NOT NULL DEFAULT 0")
        _ensure_column(cursor, "linked_accounts", "logo", "TEXT")
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
            (ticker.upper(), shares, _stored_purchase_date(purchase_date), purchase_price, brokerage),
        )
        conn.commit()
        return cursor.lastrowid


def replace_imported_transactions(
    transactions: list[dict],
    *,
    source: str,
    brokerage: str,
) -> int:
    """Replace imported transactions for a brokerage/source pair.

    Manual rows are left alone because they keep ``source='manual'``.
    Returns the number of imported rows inserted.
    """
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "DELETE FROM transactions WHERE source = ? AND brokerage = ?",
            (source, brokerage),
        )
        cursor.executemany(
            """
            INSERT INTO transactions (
                ticker,
                shares,
                purchase_date,
                purchase_price,
                brokerage,
                source,
                external_item_id,
                external_account_id,
                external_security_id,
                imported_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    row["ticker"].upper(),
                    row["shares"],
                    _stored_purchase_date(row.get("purchase_date")),
                    row["purchase_price"],
                    brokerage,
                    source,
                    row.get("external_item_id"),
                    row.get("external_account_id"),
                    row.get("external_security_id"),
                    row.get("imported_at"),
                )
                for row in transactions
            ],
        )
        conn.commit()
        return len(transactions)


def get_all_transactions() -> list[dict]:
    """Retrieve all transactions from the portfolio."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM transactions ORDER BY ticker, purchase_date")
        rows = cursor.fetchall()
        return [dict(row) for row in rows]


def update_purchase_date_for_ticker(ticker: str, purchase_date_text: str) -> int:
    """Update editable purchase dates from the holdings grid.

    Aggregated grid edits target blank Plaid-imported rows first. If there are no blank
    Plaid rows and the ticker has exactly one transaction, update that single row.
    Returns the number of rows changed.
    """
    purchase_date = parse_purchase_date(purchase_date_text)
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE transactions
            SET purchase_date = ?
            WHERE ticker = ?
              AND source = 'plaid'
              AND (purchase_date IS NULL OR purchase_date = '')
            """,
            (purchase_date, ticker.upper()),
        )
        affected = cursor.rowcount

        if affected == 0:
            cursor.execute("SELECT id FROM transactions WHERE ticker = ?", (ticker.upper(),))
            rows = cursor.fetchall()
            if len(rows) == 1:
                cursor.execute(
                    "UPDATE transactions SET purchase_date = ? WHERE id = ?",
                    (purchase_date, rows[0]["id"]),
                )
                affected = cursor.rowcount

        conn.commit()
        return affected


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
                    SUM(da.shares * da.purchase_price) / SUM(da.shares) as purchase_price
                FROM transactions da
                GROUP BY da.ticker, da.purchase_date
            )
            SELECT 
                da.ticker,
                SUM(da.shares) as total_shares,
                SUM(da.shares * da.purchase_price) / SUM(da.shares) as avg_purchase_price,
                GROUP_CONCAT(
                    CASE
                        WHEN da.purchase_date IS NULL OR da.purchase_date = '' THEN NULL
                        ELSE printf('%d/%d/%d',
                            CAST(substr(da.purchase_date, 6, 2) AS INTEGER),
                            CAST(substr(da.purchase_date, 9, 2) AS INTEGER),
                            CAST(substr(da.purchase_date, 1, 4) AS INTEGER) % 100
                        ) || ' (' || RTRIM(RTRIM(printf('%.6f', da.shares), '0'), '.') || ')'
                    END,
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


def add_linked_account(
    institution_name: str,
    institution_id: str | None,
    item_id: str,
    access_token: str,
    logo: str | None = None,
    cash_balance: float = 0.0,
    total_assets: float = 0.0,
) -> int:
    """Store a newly linked brokerage account. Returns the new record ID."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT OR REPLACE INTO linked_accounts
                (institution_name, institution_id, item_id, access_token,
                 logo, cash_balance, total_assets, linked_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """,
            (institution_name, institution_id, item_id, access_token,
             logo, cash_balance, total_assets),
        )
        conn.commit()
        return cursor.lastrowid


def get_linked_accounts() -> list[dict]:
    """Return all linked brokerage accounts."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM linked_accounts ORDER BY institution_name")
        return [dict(row) for row in cursor.fetchall()]


def update_linked_account_logo(item_id: str, logo: str) -> None:
    """Set the logo for a linked account."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE linked_accounts SET logo = ? WHERE item_id = ?", (logo, item_id))
        conn.commit()


def remove_linked_account(item_id: str) -> bool:
    """Remove a linked account and its imported transactions. Returns True if removed."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM transactions WHERE external_item_id = ?", (item_id,))
        cursor.execute("DELETE FROM linked_accounts WHERE item_id = ?", (item_id,))
        conn.commit()
        return cursor.rowcount > 0


def update_linked_account_refresh(
    item_id: str,
    cash_balance: float = 0.0,
    total_assets: float = 0.0,
) -> None:
    """Update balances and last_refreshed_at timestamp for a linked account."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """UPDATE linked_accounts
               SET cash_balance = ?, total_assets = ?, last_refreshed_at = CURRENT_TIMESTAMP
               WHERE item_id = ?""",
            (cash_balance, total_assets, item_id),
        )
        conn.commit()
