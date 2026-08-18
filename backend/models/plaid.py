"""Pydantic models for Plaid API."""

from __future__ import annotations

from pydantic import BaseModel


class PlaidConfigResponse(BaseModel):
    configured: bool
    missing: list[str]
    environment: str | None = None


class LinkTokenRequest(BaseModel):
    client_user_id: str


class LinkTokenResponse(BaseModel):
    link_token: str


class ExchangeTokenRequest(BaseModel):
    public_token: str
    metadata: dict


class ExchangeTokenResponse(BaseModel):
    success: bool
    institution_name: str
    imported_count: int
    skipped_count: int
    total_market_value: float


class LinkedAccountResponse(BaseModel):
    id: int
    institution_name: str
    institution_id: str | None
    item_id: str
    logo: str | None
    cash_balance: float
    total_assets: float
    linked_at: str | None
    last_refreshed_at: str | None


class RefreshAccountResponse(BaseModel):
    success: bool
    institution_name: str
    imported_count: int


class RefreshAllResponse(BaseModel):
    success: bool
    total_accounts: int
    successful: int
    failed: int
    results: list[dict]
