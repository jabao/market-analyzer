"""Plaid integration API endpoints.

Handles brokerage account linking via Plaid Link and holdings import.
"""

from __future__ import annotations

import os
import uuid

from fastapi import APIRouter, HTTPException

from app.plaid_integration import (
    PlaidConfigurationError,
    PlaidImportError,
    create_investments_link_token,
    create_plaid_client,
    exchange_public_token,
    get_institution_logo,
    get_investment_holdings,
    plaid_holdings_to_transactions,
)
from app.portfolio_service import (
    clear_price_cache,
    get_all_linked_accounts,
    import_plaid_portfolio,
    link_brokerage_account,
    mark_account_refreshed,
    unlink_brokerage_account,
)
from backend.models.plaid import (
    ExchangeTokenRequest,
    ExchangeTokenResponse,
    LinkTokenRequest,
    LinkTokenResponse,
    LinkedAccountResponse,
    PlaidConfigResponse,
    RefreshAccountResponse,
    RefreshAllResponse,
)

router = APIRouter()


def _resolve_plaid_config() -> dict:
    """Resolve Plaid configuration from environment variables."""
    client_id = os.environ.get("PLAID_CLIENT_ID")
    secret = os.environ.get("PLAID_SECRET")
    environment = os.environ.get("PLAID_ENV", "sandbox").lower()
    ca_bundle = os.environ.get("PLAID_CA_BUNDLE")
    connect_timeout = os.environ.get("PLAID_CONNECT_TIMEOUT_SECONDS")
    read_timeout = os.environ.get("PLAID_READ_TIMEOUT_SECONDS")

    missing = []
    if not client_id:
        missing.append("PLAID_CLIENT_ID")
    if not secret:
        missing.append("PLAID_SECRET")

    return {
        "client_id": client_id,
        "secret": secret,
        "environment": environment,
        "ca_bundle": ca_bundle,
        "connect_timeout": connect_timeout,
        "read_timeout": read_timeout,
        "missing": missing,
    }


def _make_plaid_client(config: dict):
    """Create a Plaid API client."""
    return create_plaid_client(
        config["client_id"],
        config["secret"],
        config["environment"],
        ca_bundle=config.get("ca_bundle"),
        connect_timeout=config.get("connect_timeout"),
        read_timeout=config.get("read_timeout"),
    )


@router.get("/config", response_model=PlaidConfigResponse)
async def get_plaid_config() -> PlaidConfigResponse:
    """Check if Plaid is configured."""
    config = _resolve_plaid_config()
    return PlaidConfigResponse(
        configured=len(config["missing"]) == 0,
        missing=config["missing"],
        environment=config["environment"] if not config["missing"] else None,
    )


@router.post("/link-token", response_model=LinkTokenResponse)
async def create_link_token(request: LinkTokenRequest) -> LinkTokenResponse:
    """Create a Plaid Link token for initializing Plaid Link."""
    config = _resolve_plaid_config()
    if config["missing"]:
        raise HTTPException(
            status_code=400,
            detail=f"Plaid not configured. Missing: {', '.join(config['missing'])}",
        )

    try:
        client = _make_plaid_client(config)
        link_token = create_investments_link_token(
            client,
            client_user_id=request.client_user_id,
            client_name="Market Analyzer",
        )
        return LinkTokenResponse(link_token=link_token)
    except (PlaidConfigurationError, PlaidImportError) as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create link token: {str(e)}")


@router.post("/exchange", response_model=ExchangeTokenResponse)
async def exchange_token(request: ExchangeTokenRequest) -> ExchangeTokenResponse:
    """Exchange public token for access token and import holdings."""
    config = _resolve_plaid_config()
    if config["missing"]:
        raise HTTPException(
            status_code=400,
            detail=f"Plaid not configured. Missing: {', '.join(config['missing'])}",
        )

    try:
        institution = request.metadata.get("institution") or {}
        institution_name = institution.get("name") or "Unknown Brokerage"
        institution_id = institution.get("institution_id")

        client = _make_plaid_client(config)
        exchange = exchange_public_token(client, request.public_token)
        access_token = exchange["access_token"]
        item_id = exchange.get("item_id") or str(uuid.uuid4())

        logo = get_institution_logo(client, institution_id)

        holdings_response = get_investment_holdings(client, access_token)
        import_result = plaid_holdings_to_transactions(
            holdings_response,
            item_id=item_id,
            brokerage_name=institution_name,
        )

        link_brokerage_account(
            institution_name,
            institution_id,
            item_id,
            access_token,
            logo=logo,
            cash_balance=import_result.cash_balance,
            total_assets=import_result.total_market_value,
        )

        imported_count = 0
        if import_result.transactions:
            imported_count = import_plaid_portfolio(import_result, brokerage=institution_name)

        mark_account_refreshed(
            item_id,
            cash_balance=import_result.cash_balance,
            total_assets=import_result.total_market_value,
        )
        clear_price_cache()

        return ExchangeTokenResponse(
            success=True,
            institution_name=institution_name,
            imported_count=imported_count,
            skipped_count=import_result.skipped_count,
            total_market_value=import_result.total_market_value,
        )

    except (PlaidConfigurationError, PlaidImportError) as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to exchange token: {str(e)}")


@router.get("/accounts", response_model=list[LinkedAccountResponse])
async def get_linked_accounts() -> list[LinkedAccountResponse]:
    """Get all linked brokerage accounts."""
    try:
        accounts = get_all_linked_accounts()
        return [
            LinkedAccountResponse(
                id=a["id"],
                institution_name=a["institution_name"],
                institution_id=a.get("institution_id"),
                item_id=a["item_id"],
                logo=a.get("logo"),
                cash_balance=a.get("cash_balance") or 0.0,
                total_assets=a.get("total_assets") or 0.0,
                linked_at=a.get("linked_at"),
                last_refreshed_at=a.get("last_refreshed_at"),
            )
            for a in accounts
        ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch accounts: {str(e)}")


@router.post("/accounts/{item_id}/refresh", response_model=RefreshAccountResponse)
async def refresh_account(item_id: str) -> RefreshAccountResponse:
    """Refresh holdings for a linked account."""
    config = _resolve_plaid_config()
    if config["missing"]:
        raise HTTPException(
            status_code=400,
            detail=f"Plaid not configured. Missing: {', '.join(config['missing'])}",
        )

    try:
        accounts = get_all_linked_accounts()
        account = next((a for a in accounts if a["item_id"] == item_id), None)
        if not account:
            raise HTTPException(status_code=404, detail="Account not found")

        client = _make_plaid_client(config)
        holdings_response = get_investment_holdings(client, account["access_token"])
        import_result = plaid_holdings_to_transactions(
            holdings_response,
            item_id=account["item_id"],
            brokerage_name=account["institution_name"],
        )

        imported_count = 0
        if import_result.transactions:
            imported_count = import_plaid_portfolio(
                import_result, brokerage=account["institution_name"]
            )

        mark_account_refreshed(
            account["item_id"],
            cash_balance=import_result.cash_balance,
            total_assets=import_result.total_market_value,
        )
        clear_price_cache()

        return RefreshAccountResponse(
            success=True,
            institution_name=account["institution_name"],
            imported_count=imported_count,
        )

    except (PlaidConfigurationError, PlaidImportError) as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to refresh account: {str(e)}")


@router.post("/accounts/refresh-all", response_model=RefreshAllResponse)
async def refresh_all_accounts() -> RefreshAllResponse:
    """Refresh holdings for all linked brokerage accounts."""
    config = _resolve_plaid_config()
    if config["missing"]:
        raise HTTPException(
            status_code=400,
            detail=f"Plaid not configured. Missing: {', '.join(config['missing'])}",
        )

    try:
        accounts = get_all_linked_accounts()
        if not accounts:
            return RefreshAllResponse(
                success=True,
                total_accounts=0,
                successful=0,
                failed=0,
                results=[],
            )

        client = _make_plaid_client(config)
        results = []
        successful = 0
        failed = 0

        for account in accounts:
            try:
                holdings_response = get_investment_holdings(client, account["access_token"])
                import_result = plaid_holdings_to_transactions(
                    holdings_response,
                    item_id=account["item_id"],
                    brokerage_name=account["institution_name"],
                )

                imported_count = 0
                if import_result.transactions:
                    imported_count = import_plaid_portfolio(
                        import_result, brokerage=account["institution_name"]
                    )

                mark_account_refreshed(
                    account["item_id"],
                    cash_balance=import_result.cash_balance,
                    total_assets=import_result.total_market_value,
                )

                results.append({
                    "institution_name": account["institution_name"],
                    "success": True,
                    "imported_count": imported_count,
                    "error": None,
                })
                successful += 1

            except Exception as e:
                results.append({
                    "institution_name": account["institution_name"],
                    "success": False,
                    "imported_count": 0,
                    "error": str(e),
                })
                failed += 1

        clear_price_cache()

        return RefreshAllResponse(
            success=failed == 0,
            total_accounts=len(accounts),
            successful=successful,
            failed=failed,
            results=results,
        )

    except (PlaidConfigurationError, PlaidImportError) as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to refresh accounts: {str(e)}")


@router.delete("/accounts/{item_id}")
async def delete_account(item_id: str) -> dict:
    """Unlink a brokerage account and remove its holdings."""
    try:
        success = unlink_brokerage_account(item_id)
        if success:
            clear_price_cache()
            return {"success": True, "message": "Account unlinked"}
        else:
            return {"success": False, "message": "Account not found"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to unlink account: {str(e)}")
