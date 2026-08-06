"""Plaid integration helpers for importing brokerage investment holdings."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
import os
from typing import Any, Mapping


PLAID_SOURCE = "plaid"
ROBINHOOD_BROKERAGE = "Robinhood"
PLAID_ENVIRONMENTS = {"sandbox", "development", "production"}
PLAID_CONNECT_TIMEOUT_SECONDS = 10
PLAID_READ_TIMEOUT_SECONDS = 30


class PlaidConfigurationError(RuntimeError):
    """Raised when Plaid is not installed or credentials/config are missing."""


class PlaidImportError(RuntimeError):
    """Raised when a Plaid API call or holdings conversion fails."""


@dataclass(frozen=True)
class PlaidPortfolioImport:
    transactions: list[dict]
    skipped: list[dict]
    total_market_value: float
    institution_name: str
    item_id: str | None = None

    @property
    def skipped_count(self) -> int:
        return len(self.skipped)


def _require_plaid() -> dict[str, Any]:
    try:
        from plaid import Environment
        from plaid.api import plaid_api
        from plaid.api_client import ApiClient
        from plaid.configuration import Configuration
        from plaid.model.country_code import CountryCode
        from plaid.model.institutions_search_request import InstitutionsSearchRequest
        from plaid.model.investments_holdings_get_request import InvestmentsHoldingsGetRequest
        from plaid.model.item_public_token_exchange_request import ItemPublicTokenExchangeRequest
        from plaid.model.link_token_create_request import LinkTokenCreateRequest
        from plaid.model.link_token_create_request_user import LinkTokenCreateRequestUser
        from plaid.model.products import Products
    except ImportError as exc:
        raise PlaidConfigurationError(
            "Plaid support requires plaid-python. Install dependencies with `uv pip install -r requirements.txt`."
        ) from exc

    return {
        "Environment": Environment,
        "plaid_api": plaid_api,
        "ApiClient": ApiClient,
        "Configuration": Configuration,
        "CountryCode": CountryCode,
        "InstitutionsSearchRequest": InstitutionsSearchRequest,
        "InvestmentsHoldingsGetRequest": InvestmentsHoldingsGetRequest,
        "ItemPublicTokenExchangeRequest": ItemPublicTokenExchangeRequest,
        "LinkTokenCreateRequest": LinkTokenCreateRequest,
        "LinkTokenCreateRequestUser": LinkTokenCreateRequestUser,
        "Products": Products,
    }


def _as_dict(response: Any) -> dict:
    if hasattr(response, "to_dict"):
        return response.to_dict()
    if isinstance(response, Mapping):
        return dict(response)
    raise PlaidImportError(f"Unexpected Plaid response type: {type(response)!r}")


def _number(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return float(value)
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _plaid_host(environment: str):
    plaid = _require_plaid()
    env = environment.lower()
    if env not in PLAID_ENVIRONMENTS:
        raise PlaidConfigurationError(
            f"Unsupported PLAID_ENV '{environment}'. Use one of: {', '.join(sorted(PLAID_ENVIRONMENTS))}."
        )
    hosts = {
        "sandbox": plaid["Environment"].Sandbox,
        "development": getattr(plaid["Environment"], "Development", "https://development.plaid.com"),
        "production": plaid["Environment"].Production,
    }
    return hosts[env]


def _plaid_ssl_ca_cert(ca_bundle: str | None = None) -> str | None:
    custom_bundle = ca_bundle or os.environ.get("PLAID_CA_BUNDLE")
    if custom_bundle:
        return custom_bundle

    try:
        import certifi
    except ImportError:
        return None
    return certifi.where()


def _timeout_value(value: Any, env_name: str, default: float) -> float:
    configured = value if value not in (None, "") else os.environ.get(env_name)
    return float(configured if configured not in (None, "") else default)


def _plaid_request_timeout(connect_timeout: Any = None, read_timeout: Any = None) -> tuple[float, float]:
    connect_timeout = _timeout_value(connect_timeout, "PLAID_CONNECT_TIMEOUT_SECONDS", PLAID_CONNECT_TIMEOUT_SECONDS)
    read_timeout = _timeout_value(read_timeout, "PLAID_READ_TIMEOUT_SECONDS", PLAID_READ_TIMEOUT_SECONDS)
    return (connect_timeout, read_timeout)


def _client_request_timeout(client) -> tuple[float, float]:
    return getattr(client, "_market_analyzer_request_timeout", _plaid_request_timeout())


def create_plaid_client(
    client_id: str,
    secret: str,
    environment: str = "sandbox",
    ca_bundle: str | None = None,
    connect_timeout: Any = None,
    read_timeout: Any = None,
):
    """Create an authenticated Plaid API client."""
    if not client_id or not secret:
        raise PlaidConfigurationError("PLAID_CLIENT_ID and PLAID_SECRET are required.")

    plaid = _require_plaid()
    config_kwargs = {
        "host": _plaid_host(environment),
        "api_key": {"clientId": client_id, "secret": secret},
    }
    ca_cert = _plaid_ssl_ca_cert(ca_bundle)
    if ca_cert:
        config_kwargs["ssl_ca_cert"] = ca_cert

    configuration = plaid["Configuration"](**config_kwargs)
    client = plaid["plaid_api"].PlaidApi(plaid["ApiClient"](configuration))
    client._market_analyzer_request_timeout = _plaid_request_timeout(connect_timeout, read_timeout)
    return client


def find_institution_id(client, query: str = ROBINHOOD_BROKERAGE) -> str | None:
    """Find a Plaid institution id for a brokerage name, preferring exact matches."""
    plaid = _require_plaid()
    request = plaid["InstitutionsSearchRequest"](
        query=query,
        products=[plaid["Products"]("investments")],
        country_codes=[plaid["CountryCode"]("US")],
    )
    response = _as_dict(client.institutions_search(request, _request_timeout=_client_request_timeout(client)))
    institutions = response.get("institutions") or []
    exact_query = query.casefold()

    for institution in institutions:
        if (institution.get("name") or "").casefold() == exact_query:
            return institution.get("institution_id")
    for institution in institutions:
        if exact_query in (institution.get("name") or "").casefold():
            return institution.get("institution_id")
    return None


def create_investments_link_token(
    client,
    *,
    client_user_id: str,
    client_name: str = "Market Analyzer",
    institution_id: str | None = None,
) -> str:
    """Create a Plaid Link token for investment holdings access."""
    plaid = _require_plaid()
    request_args = {
        "products": [plaid["Products"]("investments")],
        "client_name": client_name,
        "country_codes": [plaid["CountryCode"]("US")],
        "language": "en",
        "user": plaid["LinkTokenCreateRequestUser"](client_user_id=client_user_id),
    }
    if institution_id:
        request_args["institution_id"] = institution_id

    try:
        request = plaid["LinkTokenCreateRequest"](**request_args)
    except TypeError:
        request_args.pop("institution_id", None)
        request = plaid["LinkTokenCreateRequest"](**request_args)

    response = _as_dict(client.link_token_create(request, _request_timeout=_client_request_timeout(client)))
    link_token = response.get("link_token")
    if not link_token:
        raise PlaidImportError("Plaid did not return a link_token.")
    return link_token


def exchange_public_token(client, public_token: str) -> dict:
    """Exchange a Plaid Link public token for an access token and item id."""
    if not public_token:
        raise PlaidImportError("Missing Plaid public token.")

    plaid = _require_plaid()
    request = plaid["ItemPublicTokenExchangeRequest"](public_token=public_token)
    response = _as_dict(client.item_public_token_exchange(request, _request_timeout=_client_request_timeout(client)))
    access_token = response.get("access_token")
    if not access_token:
        raise PlaidImportError("Plaid did not return an access token.")
    return {"access_token": access_token, "item_id": response.get("item_id")}


def get_investment_holdings(client, access_token: str) -> dict:
    """Fetch investment holdings for an exchanged Plaid access token."""
    plaid = _require_plaid()
    request = plaid["InvestmentsHoldingsGetRequest"](access_token=access_token)
    return _as_dict(client.investments_holdings_get(request, _request_timeout=_client_request_timeout(client)))


def _security_ticker(security: Mapping[str, Any]) -> str:
    raw = security.get("ticker_symbol") or security.get("ticker") or ""
    return str(raw).strip().lstrip("$").upper()


def _is_cash_like(security: Mapping[str, Any]) -> bool:
    security_type = str(security.get("type") or "").casefold()
    security_name = str(security.get("name") or "").casefold()
    return bool(security.get("is_cash_equivalent")) or security_type in {"cash", "currency"} or security_name == "cash"


def _holding_purchase_date(holding: Mapping[str, Any], fallback: date | None) -> str | date | None:
    for key in ("purchase_date", "acquired_date", "acquisition_date"):
        value = holding.get(key)
        if value:
            return value
    return fallback


def plaid_holdings_to_transactions(
    holdings_response: Mapping[str, Any],
    *,
    item_id: str | None,
    brokerage_name: str = ROBINHOOD_BROKERAGE,
    import_date: date | None = None,
    imported_at: datetime | None = None,
) -> PlaidPortfolioImport:
    """Convert Plaid investments/holdings data into portfolio transaction rows.

    Plaid exposes current positions, not tax-lot purchase dates. Imported rows use the
    brokerage-provided purchase date only if one is present. Plaid holdings normally do
    not include tax-lot dates, so imported rows generally have an empty purchase date.
    A cost-basis-derived average price is used when Plaid provides cost basis. If cost
    basis is missing, the current institution/security price is used.
    """
    imported_timestamp = (imported_at or datetime.now()).replace(microsecond=0).isoformat(sep=" ")

    accounts = {
        account.get("account_id"): account
        for account in holdings_response.get("accounts", [])
        if account.get("account_id")
    }
    securities = {
        security.get("security_id"): security
        for security in holdings_response.get("securities", [])
        if security.get("security_id")
    }

    transactions: list[dict] = []
    skipped: list[dict] = []
    total_market_value = 0.0

    for holding in holdings_response.get("holdings", []):
        account_id = holding.get("account_id")
        security_id = holding.get("security_id")
        security = securities.get(security_id, {})
        account = accounts.get(account_id, {})

        market_value = _number(holding.get("institution_value"))
        if market_value is not None:
            total_market_value += market_value

        if _is_cash_like(security):
            skipped.append({"security_id": security_id, "reason": "cash"})
            continue

        ticker = _security_ticker(security)
        if not ticker:
            skipped.append({"security_id": security_id, "reason": "missing_ticker", "name": security.get("name")})
            continue

        shares = _number(holding.get("quantity"))
        if shares is None or shares <= 0:
            skipped.append({"ticker": ticker, "security_id": security_id, "reason": "non_positive_quantity"})
            continue

        cost_basis = _number(holding.get("cost_basis"))
        price = _number(holding.get("institution_price")) or _number(security.get("close_price"))
        purchase_price = (cost_basis / shares) if cost_basis is not None and shares else price
        if purchase_price is None or purchase_price <= 0:
            skipped.append({"ticker": ticker, "security_id": security_id, "reason": "missing_price"})
            continue

        transactions.append(
            {
                "ticker": ticker,
                "shares": shares,
                "purchase_date": _holding_purchase_date(holding, import_date),
                "purchase_price": purchase_price,
                "brokerage": brokerage_name,
                "source": PLAID_SOURCE,
                "external_item_id": item_id,
                "external_account_id": account_id,
                "external_security_id": security_id,
                "account_name": account.get("name") or account.get("official_name"),
                "security_name": security.get("name"),
                "market_value": market_value,
                "imported_at": imported_timestamp,
            }
        )

    return PlaidPortfolioImport(
        transactions=transactions,
        skipped=skipped,
        total_market_value=total_market_value,
        institution_name=brokerage_name,
        item_id=item_id,
    )
