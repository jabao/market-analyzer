"""Streamlit dashboard for browsing S&P 500 stocks ranked by a composite valuation score
and AI-powered market deep dives.

Run with:
    streamlit run dashboard.py

Two pages via sidebar navigation:
  - Market Ranking (original composite scoring)
  - AI Deep Dive Assistant (LLM-powered sector & stock analysis: Claude 4.8 / GPT 5.5)

Fixed models: Claude 4.8 (claude-opus-4-20250514) and GPT 5.5 (gpt-5).
No market context is passed to LLM - only user inputs + LLM's own knowledge.
API key can be saved via Save button (stored in session_state).
"""

from __future__ import annotations

import math
import os
from datetime import datetime

import pandas as pd
import streamlit as st
from st_aggrid import AgGrid, GridOptionsBuilder, GridUpdateMode, JsCode

from app import scoring
from app.llm import AnalysisMode, MarketAssistant
from app.llm.prompts import PROMPT_PREVIEWS, AnalysisMode as PromptMode
from app.llm.providers import ProviderType, get_default_model_for_provider
from app.service import (
    DEFAULT_PRICE_RANGE,
    PRICE_RANGES,
    build_scored_dataframe,
    get_price_history,
    get_quotes_dataframe,
    get_stock_details,
)

PAGE_SIZES = [10, 20, 50]

WEIGHT_LABELS: dict[str, str] = {
    "valuation": "Valuation (cheap)",
    "profitability": "Profitability",
    "growth": "Growth",
    "financial_health": "Financial health",
}

_FIXED_1 = "params.value.toFixed(1)"
_FIXED_2 = "params.value.toFixed(2)"
_NUMBER_FORMATS: dict[str, str] = {
    "Score": _FIXED_1,
    "Valuation": _FIXED_1,
    "Profitability": _FIXED_1,
    "Growth": _FIXED_1,
    "Health": _FIXED_1,
    "Price": "params.value.toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2})",
    "Trailing P/E": _FIXED_2,
    "Forward P/E": _FIXED_2,
    "PEG": _FIXED_2,
    "P/B": _FIXED_2,
    "Div Yield %": _FIXED_2,
    "Beta": _FIXED_2,
    "Market Cap": "params.value.toLocaleString('en-US', {maximumFractionDigits: 0})",
}

RISK_OPTIONS = ["Conservative", "Moderate", "Aggressive", "Very Aggressive"]
TIME_HORIZON_OPTIONS = ["1-3 months (short)", "6-12 months (medium)", "12+ months (long)", "3-5 years (very long)"]
INVEST_STYLE_OPTIONS = [
    "Value (cheap multiples)",
    "Growth (high growth)",
    "Balanced (GARP)",
    "Quality (high ROE, low debt)",
    "Income (dividend)",
    "Growth at Reasonable Price",
    "Quality Growth",
    "Deep Value",
]


def _formatter(expression: str) -> JsCode:
    return JsCode(f"function(params) {{ return params.value == null ? '' : {expression}; }}")


@st.cache_data(ttl=15 * 60, show_spinner="Fetching S&P 500 market data…")
def load_quotes() -> pd.DataFrame:
    return get_quotes_dataframe()


def build_grid_options(frame: pd.DataFrame, page_size: int) -> dict:
    builder = GridOptionsBuilder.from_dataframe(frame)
    builder.configure_default_column(sortable=True, filterable=True, resizable=True)
    builder.configure_selection(selection_mode="single", use_checkbox=False)
    builder.configure_pagination(
        enabled=True,
        paginationAutoPageSize=False,
        paginationPageSize=page_size,
    )
    for column, expression in _NUMBER_FORMATS.items():
        if column in frame.columns:
            builder.configure_column(
                column,
                type=["numericColumn", "numberColumnFilter"],
                valueFormatter=_formatter(expression),
            )
    options = builder.build()
    options["paginationPageSizeSelector"] = PAGE_SIZES
    return options


def format_value(value, kind: str) -> str:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return "—"
    if kind in ("text", "url"):
        return str(value)
    if kind == "price":
        return f"${value:,.2f}"
    if kind == "ratio":
        return f"{value:,.2f}"
    if kind == "percent":
        return f"{value * 100:,.2f}%"
    if kind == "large":
        return format_large(value)
    if kind == "count":
        return format_large(value, currency=False)
    if kind == "int":
        return f"{int(value):,}"
    return str(value)


def format_large(value: float, currency: bool = True) -> str:
    prefix = "$" if currency else ""
    for suffix, threshold in (("T", 1e12), ("B", 1e9), ("M", 1e6), ("K", 1e3)):
        if abs(value) >= threshold:
            return f"{prefix}{value / threshold:,.2f}{suffix}"
    return f"{prefix}{value:,.0f}"


def render_price_chart(symbol: str) -> None:
    ranges = list(PRICE_RANGES.keys())
    range_key = st.radio(
        "Price history range",
        ranges,
        index=ranges.index(DEFAULT_PRICE_RANGE),
        horizontal=True,
        key="price_range",
    )
    history = get_price_history(symbol, range_key)
    if history.empty:
        st.info(f"No price history available for {symbol} over {range_key}.")
        return
    st.line_chart(history, x="Time", y="Price", height=320)


def render_details(symbol: str) -> None:
    details = get_stock_details(symbol)
    if not details.get("found"):
        st.warning(f"No data found for '{symbol}'. Check the ticker and try again.")
        return

    st.subheader(f"🔎 {details['name']} ({details['symbol']})")
    render_price_chart(details["symbol"])
    if details.get("summary"):
        with st.expander("Business summary"):
            st.write(details["summary"])

    columns = st.columns(2)
    for index, (title, rows) in enumerate(details["sections"]):
        with columns[index % 2]:
            st.markdown(f"**{title}**")
            table = pd.DataFrame(
                {
                    "Metric": [label for label, _, _ in rows],
                    "Value": [format_value(value, kind) for _, value, kind in rows],
                }
            )
            st.dataframe(table, hide_index=True, use_container_width=True)


def selected_symbol(grid_response) -> str | None:
    selected = grid_response.get("selected_rows")
    if selected is None:
        return None
    if isinstance(selected, pd.DataFrame):
        if selected.empty:
            return None
        return selected.iloc[0]["Ticker"]
    if len(selected) > 0:
        return selected[0].get("Ticker")
    return None


def read_weights() -> dict[str, float]:
    st.subheader("Composite score weights")
    st.caption("Relative importance of each dimension. Values are normalized automatically.")
    weights: dict[str, float] = {}
    for dim in scoring.DIMENSIONS:
        default = int(scoring.DEFAULT_WEIGHTS[dim] * 100)
        weights[dim] = st.slider(WEIGHT_LABELS[dim], min_value=0, max_value=100, value=default, step=5)
    return weights


# ───────────────────────────────── Market Ranking Page ──────────────────────────────


def render_market_ranking_page():
    st.title("📊 Market Analyzer — Ranking")
    st.caption(
        "S&P 500 stocks ranked by a composite valuation score (higher = better). "
        "Tune the dimension weights in the sidebar; click a column header to sort."
    )

    with st.sidebar:
        st.header("Ranking Options")
        page_size = st.selectbox("Rows per page", PAGE_SIZES, index=0, key="ranking_page_size")
        if st.button("🔄 Refresh data", key="refresh_quotes"):
            load_quotes.clear()
        st.divider()
        weights = read_weights()

    quotes = load_quotes()
    frame = build_scored_dataframe(quotes, weights)
    if frame.empty:
        st.warning("No stock data available right now. Try refreshing.")
        return

    normalized = scoring.normalize_weights(weights)
    weight_summary = " · ".join(f"{WEIGHT_LABELS[d]}: {normalized[d] * 100:.0f}%" for d in scoring.DIMENSIONS)
    st.metric("Stocks scored", len(frame))
    st.caption(f"Current weighting — {weight_summary}")

    grid_response = AgGrid(
        frame,
        gridOptions=build_grid_options(frame, page_size),
        height=650,
        theme="streamlit",
        fit_columns_on_grid_load=True,
        allow_unsafe_jscode=True,
        update_mode=GridUpdateMode.SELECTION_CHANGED,
    )

    st.divider()
    st.subheader("Stock details")
    search = st.text_input(
        "Search any ticker", placeholder="e.g. NVDA, TSLA — or click a row above", key="ranking_search"
    ).strip().upper()

    symbol = search or selected_symbol(grid_response)
    if symbol:
        render_details(symbol)
    else:
        st.info("👆 Click any row above, or search a ticker, to see a full metric breakdown.")


# ───────────────────────────────── AI Assistant Page ──────────────────────────────


def _resolve_api_key_ui(provider: ProviderType) -> str | None:
    """Show API key input with Save button, persisting to session_state."""
    env_var = "ANTHROPIC_API_KEY" if provider == ProviderType.CLAUDE else "OPENAI_API_KEY"
    version_label = provider.display_name

    has_key = False
    key_source = None

    session_key = st.session_state.get(f"saved_{provider.value}_key") or (
        st.session_state.get("saved_api_keys", {}).get(provider.value)
        if isinstance(st.session_state.get("saved_api_keys"), dict)
        else None
    )
    if session_key:
        has_key = True
        key_source = "saved via Save button (session)"

    try:
        if env_var in st.secrets:
            has_key = True
            key_source = "streamlit secrets.toml"
        elif "llm" in st.secrets:
            llm_sec = st.secrets["llm"]
            alt = "anthropic_api_key" if provider == ProviderType.CLAUDE else "openai_api_key"
            if alt in llm_sec:
                has_key = True
                key_source = "secrets.toml [llm]"
    except Exception:
        pass

    if os.environ.get(env_var):
        has_key = True
        key_source = f"env var {env_var}"

    if has_key:
        st.success(f"✅ API key found via {key_source}.")
    else:
        st.warning(f"⚠️ No {env_var} found. Paste key below and hit Save.")

    col_input, col_save = st.columns([3, 1])

    with col_input:
        api_key_input = st.text_input(
            f"{version_label} API Key",
            type="password",
            placeholder=f"sk-... ({env_var})",
            key=f"{provider.value}_api_key_input",
            help=f"Your {version_label} key. Saved in session when you click Save.",
        )

    with col_save:
        st.write("")
        st.write("")
        if st.button("💾 Save", key=f"save_{provider.value}_key", use_container_width=True):
            key_to_save = api_key_input.strip() if api_key_input and api_key_input.strip() else None
            if key_to_save:
                st.session_state[f"saved_{provider.value}_key"] = key_to_save
                if "saved_api_keys" not in st.session_state:
                    st.session_state["saved_api_keys"] = {}
                st.session_state["saved_api_keys"][provider.value] = key_to_save
                if provider == ProviderType.CLAUDE:
                    st.session_state["saved_anthropic_key"] = key_to_save
                else:
                    st.session_state["saved_openai_key"] = key_to_save
                st.success(f"{version_label} key saved!")
                st.rerun()
            else:
                st.error("Enter a key before saving.")

    if api_key_input and api_key_input.strip():
        return api_key_input.strip()

    saved = st.session_state.get(f"saved_{provider.value}_key")
    if saved:
        return saved
    saved_dict = st.session_state.get("saved_api_keys", {})
    if isinstance(saved_dict, dict) and provider.value in saved_dict:
        return saved_dict[provider.value]

    return None


def render_ai_assistant_page():
    st.title("🤖 AI Market Deep Dive Assistant")
    st.caption(
        "Powered by **Claude 4.8** and **GPT 5.5**. No market data is passed to the LLM - analysis is based purely on your inputs + the model's own knowledge. "
        "Use the Market Ranking page separately if you want quantitative data."
    )

    col_provider, col_api = st.columns([1, 2])

    with col_provider:
        st.subheader("Model")
        provider_choice = st.radio(
            "Choose model",
            [ProviderType.CLAUDE.value, ProviderType.OPENAI.value],
            index=0,
            format_func=lambda x: ProviderType(x).display_name,
            key="llm_provider_choice",
            help="Claude 4.8 uses Anthropic, GPT 5.5 uses OpenAI",
        )
        provider = ProviderType(provider_choice)
        model_id = get_default_model_for_provider(provider)
        st.caption(f"Model ID: `{model_id}`")
        st.caption(f"Version: **{provider.display_name}**")
        st.caption("ℹ️ No market context is sent to LLM")
        stream_enabled = st.checkbox("Stream response", value=True, key="stream_enabled", help="Show tokens live as generated")

    with col_api:
        st.subheader("API Key (with Save)")
        override_api_key = _resolve_api_key_ui(provider)
        st.info("💡 Paste key and click Save to persist for session. Supports env vars or `.streamlit/secrets.toml`")

    st.divider()

    mode = st.radio(
        "Analysis Mode",
        [AnalysisMode.SECTOR.value, AnalysisMode.STOCK.value],
        index=0,
        horizontal=True,
        format_func=lambda x: "📈 Sector / Segment Recommendation" if x == "sector" else "🔍 Stock Deep Dive Picks",
        key="assistant_mode",
    )

    with st.expander("📜 View Prebuilt Expert Prompts (read-only)", expanded=False):
        prompt_info = PROMPT_PREVIEWS[PromptMode(mode)]
        st.markdown(f"**Mode:** {prompt_info['description']}")
        st.markdown("**System Prompt:**")
        st.code(prompt_info["system"], language="markdown")
        st.markdown("**User Prompt Template:**")
        st.code(prompt_info["user_template"], language="markdown")

    st.divider()

    if mode == AnalysisMode.SECTOR.value:
        from app.llm.assistant import SectorAnalysisInput

        st.subheader("📈 Sector / Segment Recommendation")
        st.info("No live market data is passed. Provide trends and news; LLM will use its own knowledge.")

        c1, c2 = st.columns(2)
        with c1:
            trends = st.text_area(
                "Current Market Trends",
                placeholder="e.g., AI CapEx boom, GLP-1 growth, reshoring, rate cuts...",
                height=140,
                key="sector_trends",
            )
            news = st.text_area(
                "Recent News / Events",
                placeholder="e.g., Fed cut rates 25bps, NVDA earnings beat...",
                height=140,
                key="sector_news",
            )
        with c2:
            additional = st.text_area(
                "Additional Constraints / Preferences",
                placeholder="e.g., Avoid crypto, focus on dividend, ESG...",
                height=100,
                key="sector_additional",
            )
            risk_tol = st.select_slider("Risk Tolerance", options=RISK_OPTIONS, value="Moderate", key="sector_risk")
            time_hor = st.select_slider("Time Horizon", options=TIME_HORIZON_OPTIONS, value="6-12 months (medium)", key="sector_horizon")
            invest_style = st.selectbox("Investment Style", INVEST_STYLE_OPTIONS, index=2, key="sector_style")

        generate_sector = st.button("🚀 Generate Sector Recommendation", type="primary", key="gen_sector")

        if generate_sector:
            try:
                assistant = MarketAssistant(provider=provider, api_key=override_api_key)
                inp = SectorAnalysisInput(
                    trends=trends,
                    news=news,
                    risk_tolerance=risk_tol,
                    time_horizon=time_hor,
                    investment_style=invest_style,
                    additional=additional,
                )

                st.subheader(f"📝 Analysis Result — {provider.display_name} (no market data)")
                result_placeholder = st.empty()

                if stream_enabled:
                    full_response = ""
                    with st.spinner(f"Asking {provider.display_name}..."):
                        try:
                            for chunk in assistant.stream_sector(inp):
                                full_response += chunk
                                result_placeholder.markdown(full_response + "▌")
                            result_placeholder.markdown(full_response)
                            st.session_state["last_sector_result"] = full_response
                            st.session_state["last_sector_model"] = provider.display_name
                            st.success("Done!")
                            st.download_button(
                                "💾 Download as Markdown",
                                full_response,
                                file_name=f"sector_analysis_{provider.value}_{datetime.now().strftime('%Y%m%d_%H%M')}.md",
                                mime="text/markdown",
                                key="dl_sector",
                            )
                        except Exception as e:
                            st.error(f"LLM call failed: {e}")
                            st.exception(e)
                else:
                    with st.spinner(f"Asking {provider.display_name}..."):
                        try:
                            result = assistant.analyze_sector(inp)
                            result_placeholder.markdown(result)
                            st.session_state["last_sector_result"] = result
                            st.session_state["last_sector_model"] = provider.display_name
                            st.download_button(
                                "💾 Download as Markdown",
                                result,
                                file_name=f"sector_analysis_{provider.value}_{datetime.now().strftime('%Y%m%d_%H%M')}.md",
                                mime="text/markdown",
                                key="dl_sector2",
                            )
                        except Exception as e:
                            st.error(f"LLM call failed: {e}")
                            st.exception(e)

            except Exception as e:
                st.error(f"Failed to init assistant: {e}")
                st.exception(e)

        if "last_sector_result" in st.session_state and not generate_sector:
            st.subheader(f"Last Sector Analysis (cached) — {st.session_state.get('last_sector_model','')}")
            st.markdown(st.session_state["last_sector_result"])

    else:
        from app.llm.assistant import StockAnalysisInput

        st.subheader("🔍 Deep Dive Stock Picks")
        st.info("No live market fundamentals are passed. LLM uses its own knowledge + your thesis.")

        custom_tickers = st.text_input(
            "Tickers (comma/space separated)",
            placeholder="e.g., NVDA, AAPL, MSFT, TSLA, or blank for general picks",
            key="custom_tickers",
        )

        ticker_list = [t.strip().upper() for t in custom_tickers.replace(";", ",").replace(" ", ",").split(",") if t.strip()]
        deduped = []
        seen = set()
        for t in ticker_list:
            if t not in seen:
                seen.add(t)
                deduped.append(t)
        tickers_str = ", ".join(deduped)

        if tickers_str:
            st.caption(f"Tickers: **{tickers_str}**")
        else:
            st.caption("No tickers - LLM will suggest general quality picks")

        c_left, c_right = st.columns(2)
        with c_left:
            thesis = st.text_area(
                "Investment Thesis / What you're looking for",
                placeholder="e.g., undervalued quality compounders, high growth AI beneficiaries...",
                height=120,
                key="stock_thesis",
            )
            trends_and_news = st.text_area(
                "Trends / News Relevant",
                placeholder="e.g., AI infra spending, FDA approvals, rate cuts...",
                height=100,
                key="stock_trends_news",
            )
            filters = st.text_area(
                "Must-have / Must-avoid filters",
                placeholder="e.g., ROE >15%, no leveraged, avoid tobacco...",
                height=80,
                key="stock_filters",
            )
        with c_right:
            additional_stock = st.text_area("Additional Notes", placeholder="Anything else...", height=80, key="stock_additional")
            focus_sector = st.text_input("Focus Sector(s) (optional)", placeholder="e.g., Technology, Healthcare", key="focus_sector")
            risk_tol_s = st.select_slider("Risk Tolerance", options=RISK_OPTIONS, value="Moderate", key="stock_risk")
            time_hor_s = st.select_slider("Time Horizon", options=TIME_HORIZON_OPTIONS, value="12+ months (long)", key="stock_horizon")
            invest_style_s = st.selectbox("Investment Style Focus", INVEST_STYLE_OPTIONS, index=6, key="stock_style")
            benchmark = st.text_input("Benchmark", value="S&P 500", key="benchmark")
            num_picks = st.slider("How many picks if general?", 1, 10, 3, key="num_picks")

        generate_stock = st.button("🚀 Generate Stock Deep Dive", type="primary", key="gen_stock")

        if generate_stock:
            try:
                assistant = MarketAssistant(provider=provider, api_key=override_api_key)
                inp = StockAnalysisInput(
                    tickers=tickers_str,
                    thesis=thesis,
                    trends_and_news=trends_and_news,
                    filters=filters,
                    additional=additional_stock,
                    focus_sector=focus_sector or "Any",
                    risk_tolerance=risk_tol_s,
                    time_horizon=time_hor_s,
                    investment_style=invest_style_s,
                    benchmark=benchmark,
                    num_picks=num_picks,
                )

                st.subheader(f"📝 Deep Dive Result — {provider.display_name} (no market data)")
                result_placeholder = st.empty()

                if stream_enabled:
                    full_response = ""
                    with st.spinner(f"Asking {provider.display_name} for deep dive..."):
                        try:
                            for chunk in assistant.stream_stocks(inp):
                                full_response += chunk
                                result_placeholder.markdown(full_response + "▌")
                            result_placeholder.markdown(full_response)
                            st.session_state["last_stock_result"] = full_response
                            st.session_state["last_stock_model"] = provider.display_name
                            st.success("Done!")
                            st.download_button(
                                "💾 Download as Markdown",
                                full_response,
                                file_name=f"stock_deepdive_{provider.value}_{datetime.now().strftime('%Y%m%d_%H%M')}.md",
                                mime="text/markdown",
                                key="dl_stock",
                            )
                        except Exception as e:
                            st.error(f"LLM call failed: {e}")
                            st.exception(e)
                else:
                    with st.spinner(f"Asking {provider.display_name} for deep dive..."):
                        try:
                            result = assistant.analyze_stocks(inp)
                            result_placeholder.markdown(result)
                            st.session_state["last_stock_result"] = result
                            st.session_state["last_stock_model"] = provider.display_name
                            st.download_button(
                                "💾 Download as Markdown",
                                result,
                                file_name=f"stock_deepdive_{provider.value}_{datetime.now().strftime('%Y%m%d_%H%M')}.md",
                                mime="text/markdown",
                                key="dl_stock2",
                            )
                        except Exception as e:
                            st.error(f"LLM call failed: {e}")
                            st.exception(e)

            except Exception as e:
                st.error(f"Failed to init assistant: {e}")
                st.exception(e)

        if "last_stock_result" in st.session_state and not generate_stock:
            st.subheader(f"Last Stock Deep Dive (cached) — {st.session_state.get('last_stock_model','')}")
            st.markdown(st.session_state["last_stock_result"])

    st.divider()
    st.caption(
        "⚠️ **Disclaimer:** This AI assistant is for informational/educational purposes only. "
        "Not financial advice. No live market data is passed to LLM - outputs are based on training knowledge and your inputs, may be outdated or hallucinated — verify facts."
    )


def main() -> None:
    st.set_page_config(page_title="Market Analyzer", layout="wide", page_icon="📊")

    with st.sidebar:
        st.title("Navigation")
        page = st.radio(
            "Go to",
            ["📊 Market Ranking", "🤖 AI Deep Dive"],
            index=0,
            key="nav_page",
        )
        st.divider()
        st.caption("Market Analyzer v2 — LLM Assistant")
        st.caption("Claude 4.8 / GPT 5.5 — no market data passed")

    if page.startswith("📊"):
        render_market_ranking_page()
    else:
        render_ai_assistant_page()


if __name__ == "__main__":
    main()
