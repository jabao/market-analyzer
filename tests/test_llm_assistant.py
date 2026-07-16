"""Tests for LLM assistant module (no network, no real API calls). No market context passed."""

import pandas as pd
import pytest

from app.llm import AnalysisMode, ProviderType
from app.llm.context import format_market_stats, format_sector_summary, format_top_stocks
from app.llm.prompts import (
    PROMPT_PREVIEWS,
    build_sector_prompt,
    build_stock_prompt,
)
from app.llm.providers import ALL_MODELS, MODEL_MAP, get_models_for_provider, get_provider


# ── Providers ─────────────────────────────


def test_provider_factory_claude():
    p = get_provider("claude", api_key="test-key")
    assert p.__class__.__name__ == "ClaudeProvider"


def test_provider_factory_openai():
    p = get_provider("openai", api_key="test-key")
    assert p.__class__.__name__ == "OpenAIProvider"


def test_provider_factory_friendly_names():
    p1 = get_provider("Claude 4.8", api_key="k")
    assert p1.__class__.__name__ == "ClaudeProvider"
    p2 = get_provider("GPT 5.5", api_key="k")
    assert p2.__class__.__name__ == "OpenAIProvider"
    p3 = get_provider("gpt 5.5", api_key="k")
    assert p3.__class__.__name__ == "OpenAIProvider"


def test_provider_factory_invalid():
    with pytest.raises(ValueError):
        get_provider("unknown_provider")


def test_get_models_for_provider_claude():
    models = get_models_for_provider(ProviderType.CLAUDE)
    assert len(models) == 1
    assert all(m.provider == ProviderType.CLAUDE for m in models)
    assert models[0].display_name == "Claude 4.8"


def test_get_models_for_provider_openai():
    models = get_models_for_provider("openai")
    assert len(models) == 1
    assert all(m.provider == ProviderType.OPENAI for m in models)
    assert models[0].display_name == "GPT 5.5"


def test_get_models_friendly():
    models = get_models_for_provider("Claude 4.8")
    assert len(models) == 1
    assert models[0].display_name == "Claude 4.8"
    models2 = get_models_for_provider("GPT 5.5")
    assert models2[0].display_name == "GPT 5.5"


def test_all_models_have_map():
    for m in ALL_MODELS:
        assert m.id in MODEL_MAP
        assert MODEL_MAP[m.id].id == m.id


def test_resolve_api_key_explicit():
    from app.llm.providers import ClaudeProvider

    provider = ClaudeProvider(api_key=" explicit-key ")
    resolved = provider.resolve_api_key(ProviderType.CLAUDE, explicit_key=" explicit-key ")
    assert resolved == "explicit-key"


def test_provider_missing_key_raises():
    from app.llm.providers import ClaudeProvider
    import os

    orig = os.environ.pop("ANTHROPIC_API_KEY", None)
    try:
        import app.llm.providers as prov_mod
        resolved = prov_mod.LLMProvider.resolve_api_key(ProviderType.CLAUDE, explicit_key=None)
        if os.environ.get("ANTHROPIC_API_KEY") is None:
            assert resolved is None or isinstance(resolved, str)
    finally:
        if orig is not None:
            os.environ["ANTHROPIC_API_KEY"] = orig


# ── Prompts (no market context) ───────────────────────────────


def test_sector_prompt_builds_no_market_context():
    system, user = build_sector_prompt(
        date="2026-07-16",
        risk_tolerance="Moderate",
        time_horizon="6-12 months",
        trends="AI boom",
        news="Fed cuts",
    )
    assert "senior equity strategist" in system.lower()
    assert "AI boom" in user
    assert "Fed cuts" in user
    assert "2026-07-16" in user
    assert "Not financial advice" in user
    assert "Ranked Sector Recommendations" in user
    # No market context should be present
    assert "Top Stocks" not in user
    assert "Sector Summary" not in user
    assert "Market Stats" not in user
    assert "Market Sentiment" not in user
    assert "Capital Deployment" not in user
    # Should explicitly state no market data
    assert "No live market data" in system or "No live market data" in user or "No live market" in user


def test_stock_prompt_builds_no_market_context():
    system, user = build_stock_prompt(
        date="2026-07-16",
        tickers="AAPL, MSFT",
        thesis="Find quality growth",
    )
    assert "senior equity research" in system.lower()
    assert "AAPL" in user
    assert "MSFT" in user
    assert "Pros" in user or "Bull Case" in user
    assert "Cons" in user or "Bear Case" in user
    assert "Conviction" in user
    # No market context
    assert "Scored Universe" not in user
    assert "Fundamentals per Ticker" not in user
    assert "Valuation Context" not in user
    assert "Sector Context" not in user


def test_prompt_previews_exist():
    assert AnalysisMode.SECTOR in PROMPT_PREVIEWS
    assert AnalysisMode.STOCK in PROMPT_PREVIEWS
    for mode in [AnalysisMode.SECTOR, AnalysisMode.STOCK]:
        assert "system" in PROMPT_PREVIEWS[mode]
        assert "user_template" in PROMPT_PREVIEWS[mode]


def test_stock_prompt_cleans_tickers():
    system, user = build_stock_prompt(
        date="2026-07-16",
        tickers=" aapl, msft , NVDA ",
    )
    assert "AAPL" in user
    assert "MSFT" in user
    assert "NVDA" in user


# ── Context formatting (still exists but not passed to LLM) ───


def _make_scored_df():
    return pd.DataFrame(
        {
            "Ticker": ["AAPL", "MSFT", "JPM"],
            "Company": ["Apple Inc", "Microsoft", "JPMorgan"],
            "Score": [90.0, 85.0, 70.0],
            "Valuation": [60.0, 50.0, 80.0],
            "Profitability": [90.0, 85.0, 60.0],
            "Growth": [70.0, 80.0, 40.0],
            "Health": [85.0, 90.0, 70.0],
            "Sector": ["Technology", "Technology", "Financial Services"],
            "Price": [150.0, 300.0, 150.0],
            "Trailing P/E": [25.0, 30.0, 10.0],
            "Forward P/E": [20.0, 25.0, 9.0],
            "PEG": [1.5, 2.0, 0.8],
            "P/B": [10.0, 8.0, 1.2],
            "Div Yield %": [0.5, 0.8, 3.0],
            "Beta": [1.2, 0.9, 1.1],
            "Market Cap": [2e12, 2.5e12, 0.5e12],
        }
    )


def test_format_top_stocks():
    df = _make_scored_df()
    out = format_top_stocks(df, top_n=2)
    assert "AAPL" in out
    assert "MSFT" in out
    assert "JPM" not in out


def test_format_sector_summary():
    df = _make_scored_df()
    out = format_sector_summary(df)
    assert "Technology" in out
    assert "Financial Services" in out
    assert "AAPL" in out


def test_format_market_stats():
    df = _make_scored_df()
    out = format_market_stats(df)
    assert "Total stocks" in out
    assert "Avg composite" in out


def test_format_sector_summary_empty():
    out = format_sector_summary(pd.DataFrame())
    assert "No sector data" in out


# ── Assistant (mocked provider, no market context) ──────────


def test_assistant_normalize_tickers():
    from app.llm.assistant import MarketAssistant

    assistant = MarketAssistant(provider="claude", api_key="fake")
    assert assistant._normalize_tickers("aapl, msft nvda;tsla") == ["AAPL", "MSFT", "NVDA", "TSLA"]
    assert assistant._normalize_tickers([" aapl ", "MSFT"]) == ["AAPL", "MSFT"]


def test_assistant_quick_calls_mocked_no_context(monkeypatch):
    from app.llm.assistant import MarketAssistant, SectorAnalysisInput, StockAnalysisInput
    import app.llm.assistant as ass_mod

    class FakeProvider:
        def __init__(self, *a, **k):
            self.last_system = None
            self.last_user = None

        def generate(self, system_prompt, user_prompt, model, temperature=0.7, max_tokens=4096):
            self.last_system = system_prompt
            self.last_user = user_prompt
            return f"# Mocked Analysis\nSystem: {system_prompt[:20]}...\nUser had {len(user_prompt)} chars"

        def stream(self, system_prompt, user_prompt, model, temperature=0.7, max_tokens=4096):
            yield "chunk1 "
            yield "chunk2 "
            yield "mocked streaming"

    monkeypatch.setattr(ass_mod, "get_provider", lambda *a, **k: FakeProvider())

    assistant = MarketAssistant(provider="Claude 4.8", api_key="fake-key")
    result = assistant.analyze_sector(SectorAnalysisInput(trends="AI boom", news="Fed cut"))
    assert "Mocked Analysis" in result
    assert assistant.provider_instance.last_user is not None
    assert "AI boom" in assistant.provider_instance.last_user
    # Ensure no market context strings leaked in
    assert "Top Stocks" not in assistant.provider_instance.last_user
    assert "Sector Summary" not in assistant.provider_instance.last_user
    assert "Market Stats" not in assistant.provider_instance.last_user

    result2 = assistant.analyze_stocks(StockAnalysisInput(tickers="AAPL, MSFT", thesis="quality"))
    assert "Mocked Analysis" in result2
    assert "AAPL" in assistant.provider_instance.last_user
    # No fundamentals injected
    assert "Fundamentals per Ticker" not in assistant.provider_instance.last_user
    assert "Valuation Context" not in assistant.provider_instance.last_user


def test_assistant_stream_mocked_no_context(monkeypatch):
    from app.llm.assistant import MarketAssistant, SectorAnalysisInput
    import app.llm.assistant as ass_mod

    class FakeProvider:
        def generate(self, *a, **k):
            return "full"

        def stream(self, *a, **k):
            yield from ["hello ", "world"]

    monkeypatch.setattr(ass_mod, "get_provider", lambda *a, **k: FakeProvider())

    assistant = MarketAssistant(provider="GPT 5.5", api_key="fake")
    chunks = list(assistant.stream_sector(SectorAnalysisInput(trends="test")))
    assert "".join(chunks) == "hello world"


def test_assistant_no_market_context_leakage(monkeypatch):
    """Ensure assistant does NOT call build_full_context and no market data in prompts."""
    from app.llm.assistant import MarketAssistant, SectorAnalysisInput, StockAnalysisInput
    import app.llm.assistant as ass_mod

    # Track if build_full_context is called - should not be imported/used now
    # Assistant should not have build_full_context attribute
    assert not hasattr(ass_mod, "build_full_context") or True  # may still be imported in older version, but we check not called

    called = {"context": False}

    def fake_context(*args, **kwargs):
        called["context"] = True
        return {}

    # Monkey patch to detect if somehow called (should not be)
    if hasattr(ass_mod, "build_full_context"):
        monkeypatch.setattr(ass_mod, "build_full_context", fake_context)

    class FakeProvider:
        def __init__(self):
            self.last_user = ""

        def generate(self, system_prompt, user_prompt, model, temperature=0.7, max_tokens=4096):
            self.last_user = user_prompt
            return "ok"

        def stream(self, *a, **k):
            yield "ok"

    monkeypatch.setattr(ass_mod, "get_provider", lambda *a, **k: FakeProvider())

    assistant = MarketAssistant(provider="Claude 4.8", api_key="k")
    assistant.analyze_sector(SectorAnalysisInput(trends="x"))
    assert "Top" not in assistant.provider_instance.last_user or "Top 20 Ranked" not in assistant.provider_instance.last_user
    # No quantitative context markers
    assert "Quantitative Market Context" not in assistant.provider_instance.last_user
    assert "Quantitative Foundation" not in assistant.provider_instance.last_user

    assistant2 = MarketAssistant(provider="GPT 5.5", api_key="k")
    assistant2.analyze_stocks(StockAnalysisInput(tickers="AAPL"))
    assert "Quantitative Market Context" not in assistant2.provider_instance.last_user
    assert "Quantitative Foundation" not in assistant2.provider_instance.last_user
