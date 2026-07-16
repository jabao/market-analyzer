"""Market Analyzer LLM Assistant package.

Exposes high-level interfaces for sector recommendation and stock deep dive modes,
with support for both Claude (Anthropic) and ChatGPT (OpenAI) providers.

Example:
    from app.llm import MarketAssistant, SectorAnalysisInput, StockAnalysisInput
    from app.llm.providers import ProviderType

    assistant = MarketAssistant(provider=ProviderType.CLAUDE, api_key="...")
    result = assistant.quick_sector_analysis(trends="AI boom", sentiment="Bullish")

    # Or with full inputs
    from app.llm.prompts import AnalysisMode
"""

from app.llm.assistant import MarketAssistant, SectorAnalysisInput, StockAnalysisInput
from app.llm.prompts import AnalysisMode
from app.llm.providers import (
    ALL_MODELS,
    DEFAULT_CLAUDE_MODEL,
    DEFAULT_OPENAI_MODEL,
    MODEL_MAP,
    ProviderType,
    get_default_model_for_provider,
    get_provider,
)

__all__ = [
    "MarketAssistant",
    "SectorAnalysisInput",
    "StockAnalysisInput",
    "AnalysisMode",
    "ProviderType",
    "get_provider",
    "get_default_model_for_provider",
    "ALL_MODELS",
    "MODEL_MAP",
    "DEFAULT_CLAUDE_MODEL",
    "DEFAULT_OPENAI_MODEL",
]
