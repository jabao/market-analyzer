"""Pydantic models for portfolio API."""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field


class AddHoldingRequest(BaseModel):
    ticker: str = Field(..., min_length=1, max_length=10)
    shares: float = Field(..., gt=0)
    purchase_date: date
    purchase_price: float = Field(..., gt=0)
    brokerage: str | None = None


class HoldingResponse(BaseModel):
    id: int
    ticker_key: str
    ticker: str
    stock_name: str
    shares: float
    avg_purchase_price: float | None
    current_price: float | None
    cost_basis: float
    current_value: float | None
    gain_loss: float | None
    gain_loss_pct: float | None
    brokerage: str


class PortfolioSummaryResponse(BaseModel):
    holdings: list[HoldingResponse]
    total_holdings: int
    total_assets: float
    total_cash: float
    invested_value: float
    net_gain_loss: float
    net_gain_loss_pct: float


class TransactionResponse(BaseModel):
    id: int
    date: str
    shares: float
    price: float
    total_value: float
    brokerage: str


class DeleteResponse(BaseModel):
    success: bool
    message: str
