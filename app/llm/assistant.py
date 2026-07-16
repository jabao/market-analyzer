"""Market Analyzer LLM Assistant orchestrator.

No market context is passed - LLM uses only user inputs + own knowledge.
Two modes:
 - analyze_sector -> str (markdown)
 - analyze_stocks -> str (markdown)

Fixed models: Claude 4.8 and GPT 5.5 (via providers.py defaults)
Temperature and max_tokens fixed internally.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Iterator, List

from app.llm.prompts import build_sector_prompt, build_stock_prompt
from app.llm.providers import ProviderType, get_default_model_for_provider, get_provider, LLMProvider


def _current_date_str() -> str:
    return datetime.now().strftime("%Y-%m-%d (%A)")


@dataclass
class SectorAnalysisInput:
    """Inputs for sector recommendation mode (no market context)."""

    trends: str = ""
    news: str = ""
    risk_tolerance: str = "Moderate"
    time_horizon: str = "6-12 months"
    investment_style: str = "Balanced (GARP)"
    additional: str = ""


@dataclass
class StockAnalysisInput:
    """Inputs for stock deep dive mode (no market context)."""

    tickers: List[str] | str = field(default_factory=list)
    thesis: str = ""
    trends_and_news: str = ""
    filters: str = ""
    additional: str = ""
    focus_sector: str = "Any"
    risk_tolerance: str = "Moderate"
    time_horizon: str = "12 months+"
    investment_style: str = "Quality Growth"
    benchmark: str = "S&P 500"
    num_picks: int = 3


class MarketAssistant:
    """High-level assistant that can generate both sector and stock analyses."""

    def __init__(
        self,
        provider: str | ProviderType = ProviderType.CLAUDE,
        model: str | None = None,
        api_key: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ):
        if isinstance(provider, str):
            lowered = provider.lower()
            if "claude" in lowered:
                provider = ProviderType.CLAUDE
            elif "gpt" in lowered or "openai" in lowered:
                provider = ProviderType.OPENAI

        self.provider_type = ProviderType(provider) if isinstance(provider, str) else provider
        self.model = model or get_default_model_for_provider(self.provider_type)
        self.api_key = api_key
        self.temperature = temperature
        self.max_tokens = max_tokens
        self._provider_instance: LLMProvider | None = None

    @property
    def provider_instance(self) -> LLMProvider:
        if self._provider_instance is None:
            self._provider_instance = get_provider(self.provider_type, api_key=self.api_key)
        return self._provider_instance

    # ── Sector ──────────────────────────────────────────────

    def analyze_sector(self, inp: SectorAnalysisInput) -> str:
        system_prompt, user_prompt = build_sector_prompt(
            date=_current_date_str(),
            risk_tolerance=inp.risk_tolerance,
            time_horizon=inp.time_horizon,
            investment_style=inp.investment_style,
            trends=inp.trends,
            news=inp.news,
            additional=inp.additional,
        )
        return self.provider_instance.generate(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            model=self.model,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
        )

    def stream_sector(self, inp: SectorAnalysisInput) -> Iterator[str]:
        system_prompt, user_prompt = build_sector_prompt(
            date=_current_date_str(),
            risk_tolerance=inp.risk_tolerance,
            time_horizon=inp.time_horizon,
            investment_style=inp.investment_style,
            trends=inp.trends,
            news=inp.news,
            additional=inp.additional,
        )
        yield from self.provider_instance.stream(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            model=self.model,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
        )

    # ── Stock ───────────────────────────────────────────────

    def _normalize_tickers(self, tickers: List[str] | str) -> List[str]:
        if isinstance(tickers, str):
            import re

            parts = re.split(r"[,\s;]+", tickers)
            return [p.strip().upper() for p in parts if p.strip()]
        return [t.strip().upper() for t in tickers if t.strip()]

    def analyze_stocks(self, inp: StockAnalysisInput) -> str:
        ticker_list = self._normalize_tickers(inp.tickers)
        # If no tickers, keep as generic - prompt will handle "no tickers specified"
        tickers_str = ", ".join(ticker_list) if ticker_list else ""

        system_prompt, user_prompt = build_stock_prompt(
            date=_current_date_str(),
            tickers=tickers_str,
            risk_tolerance=inp.risk_tolerance,
            time_horizon=inp.time_horizon,
            investment_style=inp.investment_style,
            focus_sector=inp.focus_sector,
            benchmark=inp.benchmark,
            num_picks=inp.num_picks,
            thesis=inp.thesis,
            trends_and_news=inp.trends_and_news,
            filters=inp.filters,
            additional=inp.additional,
        )

        return self.provider_instance.generate(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            model=self.model,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
        )

    def stream_stocks(self, inp: StockAnalysisInput) -> Iterator[str]:
        ticker_list = self._normalize_tickers(inp.tickers)
        tickers_str = ", ".join(ticker_list) if ticker_list else ""

        system_prompt, user_prompt = build_stock_prompt(
            date=_current_date_str(),
            tickers=tickers_str,
            risk_tolerance=inp.risk_tolerance,
            time_horizon=inp.time_horizon,
            investment_style=inp.investment_style,
            focus_sector=inp.focus_sector,
            benchmark=inp.benchmark,
            num_picks=inp.num_picks,
            thesis=inp.thesis,
            trends_and_news=inp.trends_and_news,
            filters=inp.filters,
            additional=inp.additional,
        )

        yield from self.provider_instance.stream(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            model=self.model,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
        )

    # ── Helpers ──

    def quick_sector_analysis(
        self,
        trends: str = "",
        news: str = "",
        risk_tolerance: str = "Moderate",
        time_horizon: str = "6-12 months",
    ) -> str:
        return self.analyze_sector(
            SectorAnalysisInput(
                trends=trends,
                news=news,
                risk_tolerance=risk_tolerance,
                time_horizon=time_horizon,
            )
        )

    def quick_stock_analysis(self, tickers: str | List[str], thesis: str = "") -> str:
        return self.analyze_stocks(
            StockAnalysisInput(tickers=tickers, thesis=thesis)
        )
