from datetime import date, datetime

from app import plaid_integration
from app import portfolio_db
from app.plaid_integration import plaid_holdings_to_transactions


def test_plaid_ssl_ca_cert_prefers_explicit_or_env_bundle(monkeypatch):
    monkeypatch.setenv("PLAID_CA_BUNDLE", "/tmp/env-ca.pem")

    assert plaid_integration._plaid_ssl_ca_cert() == "/tmp/env-ca.pem"
    assert plaid_integration._plaid_ssl_ca_cert("/tmp/explicit-ca.pem") == "/tmp/explicit-ca.pem"


def test_plaid_ssl_ca_cert_uses_certifi_by_default(monkeypatch):
    import certifi

    monkeypatch.delenv("PLAID_CA_BUNDLE", raising=False)

    assert plaid_integration._plaid_ssl_ca_cert() == certifi.where()


def test_plaid_request_timeout_uses_separate_connect_and_read_values(monkeypatch):
    monkeypatch.delenv("PLAID_CONNECT_TIMEOUT_SECONDS", raising=False)
    monkeypatch.delenv("PLAID_READ_TIMEOUT_SECONDS", raising=False)

    assert plaid_integration._plaid_request_timeout() == (10.0, 30.0)

    monkeypatch.setenv("PLAID_CONNECT_TIMEOUT_SECONDS", "3")
    monkeypatch.setenv("PLAID_READ_TIMEOUT_SECONDS", "45")

    assert plaid_integration._plaid_request_timeout() == (3.0, 45.0)
    assert plaid_integration._plaid_request_timeout("8", "60") == (8.0, 60.0)


def test_plaid_host_supports_development_when_sdk_constant_is_missing(monkeypatch):
    class Environment:
        Sandbox = "https://sandbox.plaid.com"
        Production = "https://production.plaid.com"

    monkeypatch.setattr(plaid_integration, "_require_plaid", lambda: {"Environment": Environment})

    assert plaid_integration._plaid_host("development") == "https://development.plaid.com"


def test_plaid_holdings_to_transactions_maps_cost_basis_and_skips_cash():
    response = {
        "accounts": [
            {"account_id": "acc-1", "name": "Robinhood Individual"},
        ],
        "securities": [
            {
                "security_id": "sec-aapl",
                "name": "Apple Inc.",
                "ticker_symbol": "aapl",
                "type": "equity",
                "close_price": 210.0,
            },
            {
                "security_id": "sec-cash",
                "name": "Cash",
                "type": "cash",
                "is_cash_equivalent": True,
            },
        ],
        "holdings": [
            {
                "account_id": "acc-1",
                "security_id": "sec-aapl",
                "quantity": 1.5,
                "cost_basis": 150.0,
                "institution_price": 220.0,
                "institution_value": 330.0,
            },
            {
                "account_id": "acc-1",
                "security_id": "sec-cash",
                "quantity": 25.0,
                "institution_value": 25.0,
            },
        ],
    }

    result = plaid_holdings_to_transactions(
        response,
        item_id="item-1",
        brokerage_name="Robinhood",
        import_date=date(2026, 7, 29),
        imported_at=datetime(2026, 7, 29, 12, 30),
    )

    assert len(result.transactions) == 1
    row = result.transactions[0]
    assert row["ticker"] == "AAPL"
    assert row["shares"] == 1.5
    assert row["purchase_date"] == date(2026, 7, 29)
    assert row["purchase_price"] == 100.0
    assert row["brokerage"] == "Robinhood"
    assert row["external_item_id"] == "item-1"
    assert row["external_account_id"] == "acc-1"
    assert row["external_security_id"] == "sec-aapl"
    assert row["imported_at"] == "2026-07-29 12:30:00"
    assert result.skipped == [{"security_id": "sec-cash", "reason": "cash"}]
    assert result.total_market_value == 355.0


def test_plaid_holdings_to_transactions_uses_current_price_when_cost_basis_missing():
    response = {
        "accounts": [{"account_id": "acc-1", "name": "Robinhood Individual"}],
        "securities": [
            {"security_id": "sec-vti", "name": "Vanguard Total Stock Market ETF", "ticker_symbol": "VTI"}
        ],
        "holdings": [
            {
                "account_id": "acc-1",
                "security_id": "sec-vti",
                "quantity": 2,
                "cost_basis": None,
                "institution_price": 250.25,
            },
        ],
    }

    result = plaid_holdings_to_transactions(response, item_id="item-1", brokerage_name="Robinhood")

    assert len(result.transactions) == 1
    assert result.transactions[0]["ticker"] == "VTI"
    assert result.transactions[0]["purchase_price"] == 250.25


def test_plaid_holdings_without_brokerage_purchase_date_imports_blank_date():
    response = {
        "accounts": [{"account_id": "acc-1", "name": "Robinhood Individual"}],
        "securities": [
            {"security_id": "sec-vti", "name": "Vanguard Total Stock Market ETF", "ticker_symbol": "VTI"}
        ],
        "holdings": [
            {
                "account_id": "acc-1",
                "security_id": "sec-vti",
                "quantity": 2,
                "cost_basis": 400,
                "institution_price": 250,
            },
        ],
    }

    result = plaid_holdings_to_transactions(response, item_id="item-1", brokerage_name="Robinhood")

    assert result.transactions[0]["purchase_date"] is None


def test_plaid_holdings_keep_brokerage_purchase_date_when_present():
    response = {
        "accounts": [{"account_id": "acc-1", "name": "Robinhood Individual"}],
        "securities": [{"security_id": "sec-aapl", "name": "Apple Inc.", "ticker_symbol": "AAPL"}],
        "holdings": [
            {
                "account_id": "acc-1",
                "security_id": "sec-aapl",
                "quantity": 1,
                "cost_basis": 100,
                "institution_price": 120,
                "purchase_date": "2026-07-29",
            },
        ],
    }

    result = plaid_holdings_to_transactions(response, item_id="item-1", brokerage_name="Robinhood")

    assert result.transactions[0]["purchase_date"] == "2026-07-29"


def test_replace_imported_transactions_leaves_manual_holdings(monkeypatch, tmp_path):
    db_path = tmp_path / "portfolio.db"
    monkeypatch.setattr(portfolio_db, "DATABASE_PATH", db_path)
    monkeypatch.setattr(portfolio_db, "DB_PATH", db_path)
    portfolio_db.init_database()

    portfolio_db.add_transaction("AAPL", 1, date(2026, 1, 1), 100, "Manual")
    portfolio_db.replace_imported_transactions(
        [
            {
                "ticker": "AAPL",
                "shares": 2.5,
                "purchase_date": date(2026, 7, 29),
                "purchase_price": 200,
                "external_item_id": "item-old",
            },
            {
                "ticker": "MSFT",
                "shares": 1,
                "purchase_date": date(2026, 7, 29),
                "purchase_price": 300,
                "external_item_id": "item-old",
            },
        ],
        source="plaid",
        brokerage="Robinhood",
    )

    inserted = portfolio_db.replace_imported_transactions(
        [
            {
                "ticker": "MSFT",
                "shares": 3.25,
                "purchase_date": date(2026, 7, 30),
                "purchase_price": 310,
                "external_item_id": "item-new",
                "external_account_id": "acc-1",
                "external_security_id": "sec-msft",
                "imported_at": "2026-07-30 09:00:00",
            },
        ],
        source="plaid",
        brokerage="Robinhood",
    )

    rows = portfolio_db.get_all_transactions()
    assert inserted == 1
    assert len(rows) == 2
    assert {row["ticker"] for row in rows} == {"AAPL", "MSFT"}

    manual = next(row for row in rows if row["ticker"] == "AAPL")
    imported = next(row for row in rows if row["ticker"] == "MSFT")
    assert manual["source"] == "manual"
    assert manual["brokerage"] == "Manual"
    assert imported["source"] == "plaid"
    assert imported["brokerage"] == "Robinhood"
    assert imported["external_item_id"] == "item-new"

    aggregated = portfolio_db.get_aggregated_holdings()
    msft = next(row for row in aggregated if row["ticker"] == "MSFT")
    assert msft["total_shares"] == 3.25
    assert msft["purchase_dates_str"] == "7/30/26 (3.25)"


def test_imported_blank_purchase_date_is_hidden_and_editable(monkeypatch, tmp_path):
    db_path = tmp_path / "portfolio.db"
    monkeypatch.setattr(portfolio_db, "DATABASE_PATH", db_path)
    monkeypatch.setattr(portfolio_db, "DB_PATH", db_path)
    portfolio_db.init_database()

    portfolio_db.replace_imported_transactions(
        [
            {
                "ticker": "VTI",
                "shares": 2,
                "purchase_date": None,
                "purchase_price": 200,
                "external_item_id": "item-new",
            },
        ],
        source="plaid",
        brokerage="Robinhood",
    )

    rows = portfolio_db.get_all_transactions()
    assert rows[0]["purchase_date"] == ""
    assert portfolio_db.get_aggregated_holdings()[0]["purchase_dates_str"] is None

    changed = portfolio_db.update_purchase_date_for_ticker("VTI", "7/29/26")

    assert changed == 1
    rows = portfolio_db.get_all_transactions()
    assert rows[0]["purchase_date"] == "2026-07-29"
    assert portfolio_db.get_aggregated_holdings()[0]["purchase_dates_str"] == "7/29/26 (2)"
