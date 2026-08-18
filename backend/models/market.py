"""Pydantic models for market data API."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class WeightsRequest(BaseModel):
    valuation: float = Field(40.0, ge=0, le=100)
    profitability: float = Field(30.0, ge=0, le=100)
    growth: float = Field(20.0, ge=0, le=100)
    financial_health: float = Field(10.0, ge=0, le=100)


class ScoredStocksRequest(BaseModel):
    weights: WeightsRequest | None = None


class StockDetailsResponse(BaseModel):
    symbol: str
    found: bool
    name: str
    summary: str | None = None
    sections: list[tuple[str, list[tuple[str, Any, str]]]]


class PriceHistoryPoint(BaseModel):
    time: str
    price: float


class RefreshResponse(BaseModel):
    status: str
    message: str
