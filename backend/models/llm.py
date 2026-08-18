"""Pydantic models for LLM assistant API."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class SectorAnalysisRequest(BaseModel):
    provider: Literal["claude", "openai"] = Field(default="claude")
    api_key: str | None = None
    trends: str = ""
    news: str = ""
    risk_tolerance: str = "Moderate"
    time_horizon: str = "6-12 months (medium)"
    investment_style: str = "Balanced (GARP)"
    additional: str = ""
    stream: bool = True


class StockAnalysisRequest(BaseModel):
    provider: Literal["claude", "openai"] = Field(default="claude")
    api_key: str | None = None
    tickers: str = ""
    thesis: str = ""
    trends_and_news: str = ""
    filters: str = ""
    additional: str = ""
    focus_sector: str = "Any"
    risk_tolerance: str = "Moderate"
    time_horizon: str = "12+ months (long)"
    investment_style: str = "Quality Growth"
    benchmark: str = "S&P 500"
    num_picks: int = Field(default=3, ge=1, le=10)
    stream: bool = True


class AnalysisResponse(BaseModel):
    content: str
    provider: str
    model: str


class ProviderInfo(BaseModel):
    id: str
    name: str
    display_name: str
    default_model: str
