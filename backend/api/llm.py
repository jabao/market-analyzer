"""LLM assistant API endpoints.

Provides AI-powered market analysis using Claude or OpenAI.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from app.llm.assistant import MarketAssistant, SectorAnalysisInput, StockAnalysisInput
from app.llm.providers import ProviderType, get_default_model_for_provider
from backend.models.llm import (
    AnalysisResponse,
    ProviderInfo,
    SectorAnalysisRequest,
    StockAnalysisRequest,
)

router = APIRouter()


@router.get("/providers", response_model=list[ProviderInfo])
async def get_providers() -> list[ProviderInfo]:
    """Get available LLM providers and their models."""
    return [
        ProviderInfo(
            id=ProviderType.CLAUDE.value,
            name="Claude",
            display_name=ProviderType.CLAUDE.display_name,
            default_model=get_default_model_for_provider(ProviderType.CLAUDE),
        ),
        ProviderInfo(
            id=ProviderType.OPENAI.value,
            name="OpenAI",
            display_name=ProviderType.OPENAI.display_name,
            default_model=get_default_model_for_provider(ProviderType.OPENAI),
        ),
    ]


@router.post("/sector-analysis")
async def analyze_sector(request: SectorAnalysisRequest):
    """Generate sector/market segment analysis."""
    try:
        provider = ProviderType(request.provider)
        assistant = MarketAssistant(provider=provider, api_key=request.api_key)

        inp = SectorAnalysisInput(
            trends=request.trends,
            news=request.news,
            risk_tolerance=request.risk_tolerance,
            time_horizon=request.time_horizon,
            investment_style=request.investment_style,
            additional=request.additional,
        )

        if request.stream:
            async def generate():
                try:
                    for chunk in assistant.stream_sector(inp):
                        yield f"data: {chunk}\n\n"
                    yield "data: [DONE]\n\n"
                except Exception as e:
                    yield f"data: ERROR: {str(e)}\n\n"

            return StreamingResponse(
                generate(),
                media_type="text/event-stream",
                headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
            )
        else:
            result = assistant.analyze_sector(inp)
            return AnalysisResponse(
                content=result,
                provider=provider.value,
                model=get_default_model_for_provider(provider),
            )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Sector analysis failed: {str(e)}")


@router.post("/stock-analysis")
async def analyze_stocks(request: StockAnalysisRequest):
    """Generate deep dive stock analysis."""
    try:
        provider = ProviderType(request.provider)
        assistant = MarketAssistant(provider=provider, api_key=request.api_key)

        inp = StockAnalysisInput(
            tickers=request.tickers,
            thesis=request.thesis,
            trends_and_news=request.trends_and_news,
            filters=request.filters,
            additional=request.additional,
            focus_sector=request.focus_sector,
            risk_tolerance=request.risk_tolerance,
            time_horizon=request.time_horizon,
            investment_style=request.investment_style,
            benchmark=request.benchmark,
            num_picks=request.num_picks,
        )

        if request.stream:
            async def generate():
                try:
                    for chunk in assistant.stream_stocks(inp):
                        yield f"data: {chunk}\n\n"
                    yield "data: [DONE]\n\n"
                except Exception as e:
                    yield f"data: ERROR: {str(e)}\n\n"

            return StreamingResponse(
                generate(),
                media_type="text/event-stream",
                headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
            )
        else:
            result = assistant.analyze_stocks(inp)
            return AnalysisResponse(
                content=result,
                provider=provider.value,
                model=get_default_model_for_provider(provider),
            )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Stock analysis failed: {str(e)}")
