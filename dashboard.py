"""Streamlit dashboard for browsing S&P 500 stocks ranked by a composite valuation score
and AI-powered market deep dives.

Run with:
    streamlit run dashboard.py

Three pages via sidebar navigation:
  - Market Ranking (original composite scoring)
  - AI Deep Dive Assistant (LLM-powered sector & stock analysis: Claude 4.8 / GPT 5.5)
  - Portfolio Tracker (manage personal stock portfolio with live prices)

Fixed models: Claude 4.8 (claude-opus-4-20250514) and GPT 5.5 (gpt-5).
No market context is passed to LLM - only user inputs + LLM's own knowledge.
API key can be saved via Save button (stored in session_state).
"""

from __future__ import annotations

import math
import os
import time
import uuid
from datetime import datetime

import yfinance as yf
import pandas as pd
import streamlit as st
from st_aggrid import AgGrid, GridOptionsBuilder, GridUpdateMode, JsCode

from app import scoring
from app.llm import AnalysisMode, MarketAssistant
from app.llm.prompts import PROMPT_PREVIEWS, AnalysisMode as PromptMode
from app.llm.providers import ProviderType, get_default_model_for_provider
from app.portfolio_db import init_database as init_portfolio_db
from app.portfolio_service import (
    add_portfolio_holding,
    calculate_portfolio_summary,
    clear_price_cache,
    delete_all_transactions_for_ticker,
    delete_portfolio_holding,
    get_ticker_positions,
    get_current_prices_batch,
    get_portfolio_holdings,
    import_plaid_portfolio,
    update_holding_purchase_date,
)
from app.plaid_integration import (
    ROBINHOOD_BROKERAGE,
    PlaidConfigurationError,
    PlaidImportError,
    create_investments_link_token,
    create_plaid_client,
    exchange_public_token,
    get_investment_holdings,
    plaid_holdings_to_transactions,
)
from app.plaid_link_component import plaid_link_button
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


def _secret_value(*keys: str) -> str | None:
    try:
        for key in keys:
            if key in st.secrets:
                return str(st.secrets[key])
    except Exception:
        return None
    return None


def _nested_secret_value(section: str, *keys: str) -> str | None:
    try:
        if section not in st.secrets:
            return None
        values = st.secrets[section]
        for key in keys:
            if key in values:
                return str(values[key])
    except Exception:
        return None
    return None


def _resolve_plaid_config() -> dict:
    client_id = (
        os.environ.get("PLAID_CLIENT_ID")
        or _secret_value("PLAID_CLIENT_ID")
        or _nested_secret_value("plaid", "client_id", "PLAID_CLIENT_ID")
    )
    secret = (
        os.environ.get("PLAID_SECRET")
        or _secret_value("PLAID_SECRET")
        or _nested_secret_value("plaid", "secret", "PLAID_SECRET")
    )
    environment = (
        os.environ.get("PLAID_ENV")
        or _secret_value("PLAID_ENV")
        or _nested_secret_value("plaid", "env", "environment", "PLAID_ENV")
        or "sandbox"
    )
    robinhood_institution_id = (
        os.environ.get("PLAID_ROBINHOOD_INSTITUTION_ID")
        or _secret_value("PLAID_ROBINHOOD_INSTITUTION_ID")
        or _nested_secret_value("plaid", "robinhood_institution_id", "PLAID_ROBINHOOD_INSTITUTION_ID")
        or st.session_state.get("plaid_robinhood_institution_id")
    )
    ca_bundle = (
        os.environ.get("PLAID_CA_BUNDLE")
        or _secret_value("PLAID_CA_BUNDLE")
        or _nested_secret_value("plaid", "ca_bundle", "PLAID_CA_BUNDLE")
    )
    connect_timeout = (
        os.environ.get("PLAID_CONNECT_TIMEOUT_SECONDS")
        or _secret_value("PLAID_CONNECT_TIMEOUT_SECONDS")
        or _nested_secret_value("plaid", "connect_timeout_seconds", "PLAID_CONNECT_TIMEOUT_SECONDS")
    )
    read_timeout = (
        os.environ.get("PLAID_READ_TIMEOUT_SECONDS")
        or _secret_value("PLAID_READ_TIMEOUT_SECONDS")
        or _nested_secret_value("plaid", "read_timeout_seconds", "PLAID_READ_TIMEOUT_SECONDS")
    )

    missing = []
    if not client_id:
        missing.append("PLAID_CLIENT_ID")
    if not secret:
        missing.append("PLAID_SECRET")

    return {
        "client_id": client_id,
        "secret": secret,
        "environment": environment.lower(),
        "robinhood_institution_id": robinhood_institution_id,
        "ca_bundle": ca_bundle,
        "connect_timeout": connect_timeout,
        "read_timeout": read_timeout,
        "missing": missing,
    }


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


# ───────────────────────────── Portfolio Tracker Page ─────────────────────────────


def _ensure_plaid_client_user_id() -> str:
    if "plaid_client_user_id" not in st.session_state:
        st.session_state["plaid_client_user_id"] = f"market-analyzer-{uuid.uuid4()}"
    return st.session_state["plaid_client_user_id"]


def _prepare_robinhood_link_token(config: dict, *, auto_open: bool = False) -> None:
    client = create_plaid_client(
        config["client_id"],
        config["secret"],
        config["environment"],
        ca_bundle=config.get("ca_bundle"),
        connect_timeout=config.get("connect_timeout"),
        read_timeout=config.get("read_timeout"),
    )
    institution_id = config.get("robinhood_institution_id")

    link_token = create_investments_link_token(
        client,
        client_user_id=_ensure_plaid_client_user_id(),
        client_name="Market Analyzer",
        institution_id=institution_id,
    )
    st.session_state["plaid_robinhood_link_token"] = link_token
    st.session_state["plaid_robinhood_auto_open"] = auto_open
    st.session_state["plaid_robinhood_launch_id"] = str(uuid.uuid4())
    st.session_state.pop("plaid_robinhood_link_error", None)


def _clear_robinhood_link_state() -> None:
    st.session_state.pop("plaid_robinhood_link_token", None)
    st.session_state.pop("plaid_robinhood_auto_open", None)
    st.session_state.pop("plaid_robinhood_launch_id", None)
    st.session_state.pop("plaid_robinhood_popup_id", None)
    st.session_state.pop("plaid_last_prepare_popup_id", None)
    st.session_state.pop("plaid_last_processed_public_token", None)
    st.session_state.pop("plaid_robinhood_link_error", None)


def _import_robinhood_public_token(public_token: str, metadata: dict, config: dict) -> bool:
    institution = metadata.get("institution") or {}
    institution_name = institution.get("name") or ROBINHOOD_BROKERAGE
    if config["environment"] != "sandbox" and "robinhood" not in institution_name.casefold():
        st.error(f"Selected institution was {institution_name}. Please connect Robinhood for this importer.")
        return False

    client = create_plaid_client(
        config["client_id"],
        config["secret"],
        config["environment"],
        ca_bundle=config.get("ca_bundle"),
        connect_timeout=config.get("connect_timeout"),
        read_timeout=config.get("read_timeout"),
    )
    exchange = exchange_public_token(client, public_token)
    holdings_response = get_investment_holdings(client, exchange["access_token"])
    import_result = plaid_holdings_to_transactions(
        holdings_response,
        item_id=exchange.get("item_id"),
        brokerage_name=ROBINHOOD_BROKERAGE,
    )

    if not import_result.transactions:
        st.warning("Plaid returned no ticker-based Robinhood holdings to import.")
        if import_result.skipped_count:
            st.caption(f"Skipped {import_result.skipped_count} cash or unsupported holdings.")
        return False

    imported_count = import_plaid_portfolio(import_result, brokerage=ROBINHOOD_BROKERAGE)
    clear_price_cache()
    st.session_state["plaid_robinhood_last_import"] = {
        "imported_count": imported_count,
        "skipped_count": import_result.skipped_count,
        "total_market_value": import_result.total_market_value,
        "imported_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    st.session_state.pop("plaid_robinhood_link_token", None)
    st.session_state.pop("plaid_robinhood_popup_id", None)
    return True


def render_brokerage_import_panel() -> None:
    with st.expander("Import From Robinhood", expanded=bool(st.session_state.get("plaid_robinhood_link_token"))):
        config = _resolve_plaid_config()
        last_import = st.session_state.get("plaid_robinhood_last_import")
        if last_import:
            st.success(
                f"Last import: {last_import['imported_count']} holdings at {last_import['imported_at']} "
                f"(skipped {last_import['skipped_count']})."
            )

        if config["missing"]:
            st.warning(
                "Plaid credentials are not configured. Set "
                f"{', '.join(config['missing'])} and optional PLAID_ENV."
            )
            return

        st.caption(f"Plaid environment: {config['environment']} · Product: investments")
        if not config.get("robinhood_institution_id"):
            st.caption("Optional: set PLAID_ROBINHOOD_INSTITUTION_ID to skip Plaid institution selection.")

        link_token = st.session_state.get("plaid_robinhood_link_token")
        link_error = st.session_state.get("plaid_robinhood_link_error")
        if link_error:
            st.error(link_error)

        if not link_token:
            link_result = plaid_link_button(
                None,
                label="Start Robinhood Login",
                prepare_mode=True,
                popup_mode=True,
                key="plaid_robinhood_link",
            )
            if not link_result:
                return

            if link_result.get("event") == "open_failed":
                st.warning("The browser blocked the popup. Allow popups for this page and try again.")
                return

            if link_result.get("event") == "prepare_requested":
                popup_id = link_result.get("popup_id")
                if popup_id and popup_id == st.session_state.get("plaid_last_prepare_popup_id"):
                    return

                st.session_state["plaid_last_prepare_popup_id"] = popup_id
                try:
                    with st.spinner("Preparing Robinhood login..."):
                        _prepare_robinhood_link_token(config, auto_open=False)
                    st.session_state["plaid_robinhood_popup_id"] = popup_id
                    st.rerun()
                except (PlaidConfigurationError, PlaidImportError) as exc:
                    st.session_state["plaid_robinhood_link_error"] = str(exc)
                    st.rerun()
                except Exception as exc:
                    st.session_state["plaid_robinhood_link_error"] = f"Failed to create Plaid Link token: {exc}"
                    st.rerun()
            return

        if not link_token:
            return

        st.caption("A separate login window should be open. If it did not load Plaid Link, click the button below.")
        link_result = plaid_link_button(
            link_token,
            label="Open Robinhood Login",
            auto_open=bool(st.session_state.get("plaid_robinhood_auto_open")),
            launch_id=st.session_state.get("plaid_robinhood_launch_id"),
            popup_id=st.session_state.get("plaid_robinhood_popup_id"),
            key="plaid_robinhood_link",
        )

        if st.button("Refresh Login Token", use_container_width=True, key="plaid_reset_robinhood"):
            _clear_robinhood_link_state()
            st.rerun()

        if not link_result:
            return

        if link_result.get("event") == "open_failed":
            st.session_state["plaid_robinhood_auto_open"] = False
            st.warning("The browser blocked the automatic Plaid popup. Click Connect Robinhood to continue.")
            return

        if link_result.get("event") == "exit":
            st.session_state["plaid_robinhood_auto_open"] = False
            error = link_result.get("error")
            if error:
                st.error(f"Plaid Link exited with an error: {error}")
            return

        public_token = link_result.get("public_token")
        if not public_token or public_token == st.session_state.get("plaid_last_processed_public_token"):
            return

        st.session_state["plaid_robinhood_auto_open"] = False
        st.session_state["plaid_last_processed_public_token"] = public_token
        try:
            with st.spinner("Importing Robinhood holdings from Plaid..."):
                imported = _import_robinhood_public_token(public_token, link_result.get("metadata") or {}, config)
            if imported:
                st.rerun()
        except (PlaidConfigurationError, PlaidImportError) as exc:
            st.error(str(exc))
        except Exception as exc:
            st.error(f"Failed to import Robinhood holdings: {exc}")


def render_portfolio_page():
    """Render the portfolio tracking page with holdings table, add form, and live prices."""
    st.title("💼 Portfolio Tracker")
    st.caption(
        "Track your stock portfolio with real-time price updates. "
        "Prices refresh automatically every 30 seconds or click Refresh."
    )

    # Auto-refresh setup (every 30 seconds)
    if "portfolio_last_refresh" not in st.session_state:
        st.session_state["portfolio_last_refresh"] = time.time()

    current_time = time.time()
    if current_time - st.session_state["portfolio_last_refresh"] >= 30:
        clear_price_cache()
        st.session_state["portfolio_last_refresh"] = current_time
        st.rerun()

    # Initialize database on first load
    init_portfolio_db()
    render_brokerage_import_panel()

    # Layout columns for metrics
    cols = st.columns(4)

    # Get all holdings
    holdings = get_portfolio_holdings()
    tickers = [h["ticker"] for h in holdings]

    # Fetch live prices
    prices = get_current_prices_batch(tickers) if tickers else {}

    # Calculate summary
    if holdings:
        summary = calculate_portfolio_summary(holdings, prices)
        rows = summary["rows"]
        total_cost = summary["total_cost_basis"]
        total_value = summary["total_current_value"]
        total_gain_loss = summary["total_gain_loss"]
        total_gain_pct = summary["total_gain_loss_pct"]
    else:
        rows = []
        total_cost = 0.0
        total_value = 0.0
        total_gain_loss = 0.0
        total_gain_pct = 0.0

    # Display summary metrics at top
    cols[0].metric("Total Holdings", len(holdings))
    cols[1].metric("Total Cost Basis", format_large(total_cost, currency=True))
    cols[2].metric("Current Value", format_large(total_value, currency=True))

    # Format gain/loss with color
    if total_gain_loss >= 0:
        gl_display = f"+{format_large(total_gain_loss, currency=True)} (+{total_gain_pct:.2f}%)"
    else:
        gl_display = f"{format_large(total_gain_loss, currency=True)} ({total_gain_pct:.2f}%)"
    cols[3].metric("Net Gain/Loss", gl_display)

    st.divider()

    # Show holdings table (if there are any)
    col_refresh, _ = st.columns([1, 3])
    with col_refresh:
        if st.button("🔄 Refresh Prices", use_container_width=True, key="portfolio_refresh"):
            clear_price_cache()
            st.rerun()

    viewing = st.session_state.get("viewing_transactions")

    if holdings:
        st.subheader("Your Holdings")
        
        # Build DataFrame for display
        df = pd.DataFrame(rows)
        original_purchase_dates = df.set_index("ticker_key")["Purchase Dates"].to_dict()

        # Configure grid options for portfolio
        builder = GridOptionsBuilder.from_dataframe(df)
        builder.configure_default_column(sortable=True, filterable=True, resizable=True)
        builder.configure_selection(selection_mode="single", use_checkbox=False)
        builder.configure_pagination(enabled=False)

        # Format numeric columns
        numeric_cols = ["Shares", "Avg Purchase Price", "Current Price", "Cost Basis", "Current Value", "Gain/Loss", "Gain/Loss %"]
        for col in numeric_cols:
            if col == "Gain/Loss %":
                expr = f"params.value === null ? '' : params.value.toFixed(2) + '%'"
            elif col in ["Current Price", "Purchase Price"]:
                expr = "params.value === null || isNaN(params.value) ? '-' : '$' + params.value.toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2})"
            elif col == "Shares":
                expr = "params.value === null ? '' : params.value.toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2})"
            elif col == "Gain/Loss":
                expr = "params.value === null || isNaN(params.value) ? '-' : (params.value < 0 ? '-$' : '$') + Math.abs(params.value).toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2})"
            else:
                expr = "params.value === null || isNaN(params.value) ? '-' : '$' + params.value.toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2})"
            builder.configure_column(col, type=["numericColumn"], valueFormatter=_formatter(expr))

        # Edits apply to blank imported rows for the ticker, or a single-row ticker.
        builder.configure_column(
            "Purchase Dates",
            width=250,
            editable=True,
            cellEditor="agTextCellEditor",
            headerTooltip="Editable. Use YYYY-MM-DD or M/D/YY.",
        )

        options = builder.build()
        options["stopEditingWhenCellsLoseFocus"] = True

        # Render the portfolio table
        grid_response = AgGrid(
            df,
            gridOptions=options,
            height=500,
            theme="streamlit",
            fit_columns_on_grid_load=True,
            allow_unsafe_jscode=True,
            update_mode=GridUpdateMode.SELECTION_CHANGED | GridUpdateMode.VALUE_CHANGED,
            key="portfolio_grid",
        )

        edited_data = grid_response.get("data")
        if edited_data is not None:
            edited_df = edited_data if isinstance(edited_data, pd.DataFrame) else pd.DataFrame(edited_data)
            for _, edited_row in edited_df.iterrows():
                ticker = edited_row.get("ticker_key")
                if not ticker:
                    continue
                old_value = str(original_purchase_dates.get(ticker) or "").strip()
                new_value = str(edited_row.get("Purchase Dates") or "").strip()
                if new_value == old_value:
                    continue

                try:
                    changed = update_holding_purchase_date(ticker, new_value)
                except ValueError as exc:
                    st.error(f"Invalid purchase date for {ticker}: {exc}")
                    break

                if changed:
                    st.success(f"Updated purchase date for {ticker}.")
                    st.rerun()
                else:
                    st.warning(f"No editable imported purchase date found for {ticker}.")
                break

        # Delete/view buttons for selected row
        selected = grid_response.get("selected_rows")
        if selected is not None and len(selected) > 0:
            selected_ticker = selected.iloc[0].get("ticker_key")
            if selected_ticker:
                st.caption(f"Selected: **{selected_ticker}**")
                
                col_view, col_delete = st.columns(2)
                with col_view:
                    if st.button("📋 View Transactions", key="view_txn_btn"):
                        st.session_state["viewing_transactions"] = selected_ticker
                        st.rerun()
                with col_delete:
                    if st.button("🗑️ Delete All Positions for " + selected_ticker, type="secondary", key="delete_holding_btn"):
                        confirm_del = st.text_input("Type '" + selected_ticker + "' to confirm:", key="confirm_del_input")
                        if confirm_del == selected_ticker:
                            if delete_all_transactions_for_ticker(selected_ticker):
                                st.success(f"All positions for {selected_ticker} deleted!")
                                st.rerun()
                            else:
                                st.error(f"Failed to delete {selected_ticker}.")

        st.divider()

        # View individual transactions for a ticker
        if viewing:
            if st.button("← Back to Portfolio", key="back_to_portfolio"):
                st.session_state.pop("viewing_transactions", None)
                st.rerun()

            st.subheader(f"📋 Transaction History: {viewing}")
            transactions = get_ticker_positions(viewing)

            if not transactions:
                st.info("No transactions found for this ticker.")
            else:
                txn_df = pd.DataFrame([{
                    "ID": t["id"],
                    "Date": t["purchase_date"],
                    "Shares": t["shares"],
                    "Price": t["purchase_price"],
                    "Total Value": round(t["shares"] * t["purchase_price"], 2),
                    "Brokerage": t.get("brokerage") or ""
                } for t in transactions])

                col_delete_txn, _ = st.columns([1, 4])
                with col_delete_txn:
                    delete_txn_id = st.number_input("Transaction ID to delete:", min_value=1, key="delete_txn_id")

                grid_col, delete_btn_col = st.columns([3, 1])
                with grid_col:
                    st.dataframe(txn_df, hide_index=True, use_container_width=False)

                with delete_btn_col:
                    if st.button("Delete TXN", type="secondary", key="delete_single_txn"):
                        if delete_portfolio_holding(delete_txn_id):
                            st.success("Transaction deleted!")
                            st.rerun()
                        else:
                            st.error("Failed to delete transaction.")

            st.divider()

    elif not viewing:
        # No holdings - show empty state message
        st.info("👆 No holdings yet. Use 'Add New Holding' below to get started!")
        st.divider()

    # Add new holding form appears at the end regardless of holdings status
    render_add_holding_form()


def render_add_holding_form():
    """Render the add holding form as a helper function."""
    with st.expander("➕ Add New Holding", expanded=True):
        col1, col2 = st.columns(2)

        with col1:
            add_ticker_raw = st.text_input(
                "Ticker Symbol",
                placeholder="e.g., AAPL, MSFT (required)",
                key="add_ticker",
                help="Stock ticker symbol (required, will be converted to uppercase)",
            )
            add_ticker = add_ticker_raw.strip().upper() if add_ticker_raw else ""

            add_brokerage = st.text_input(
                "Brokerage",
                placeholder="e.g., Fidelity, Robinhood, E*TRADE",
                key="add_brokerage",
                help="Which brokerage holds this position (optional)",
            ).strip()

        with col2:
            add_shares = st.number_input(
                "Number of Shares",
                min_value=0.01,
                value=1.0,
                step=0.01,
                key="add_shares",
                help="Number of shares owned",
            )

            add_purchase_price = st.number_input(
                "Purchase Price ($)",
                min_value=0.01,
                value=100.0,
                step=0.01,
                key="add_price",
                help="Average purchase price per share",
            )

            add_purchase_date = st.date_input(
                "Purchase Date",
                value=datetime.now(),
                key="add_date",
                help="Date when you purchased these shares",
            )

        col_save, _ = st.columns([2, 1])
        with col_save:
            if st.button("💾 Add Holding", type="primary", use_container_width=True, key="btn_add_holding"):
                if not add_ticker:
                    st.error("Please enter a ticker symbol.")
                elif add_shares <= 0:
                    st.error("Please enter a valid number of shares.")
                elif add_purchase_price <= 0:
                    st.error("Please enter a valid purchase price.")
                else:
                    try:
                        holding_id = add_portfolio_holding(
                            ticker=add_ticker,
                            shares=float(add_shares),
                            purchase_date=add_purchase_date,
                            purchase_price=float(add_purchase_price),
                            brokerage=add_brokerage if add_brokerage else None,
                        )
                        st.success(f"Holding added successfully! (ID: {holding_id})")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Failed to add holding: {e}")

    st.divider()
    st.caption(
        "💡 Tip: Prices are fetched from Yahoo Finance and cached for 30 seconds. "
        "Same tickers are automatically combined with weighted average price. "
        "Click Refresh to force an immediate update. Click a row's ticker to view/delete individual transactions."
    )


def main() -> None:
    st.set_page_config(page_title="Market Analyzer", layout="wide", page_icon="📊")

    # Initialize default page in session state
    if "current_page" not in st.session_state:
        st.session_state["current_page"] = "📊 Market Ranking"

    # Apply custom CSS for tab-like buttons
    st.markdown("""
    <style>
    .stButton button {
        border-radius: 8px !important;
        padding: 0.5rem 1rem !important;
    }
    </style>
    """, unsafe_allow_html=True)

    # Top navigation tabs (centered)
    tab_col1, tab_col2, tab_col3 = st.columns([1, 1, 1], gap="small")
    with tab_col1:
        btn1 = st.button("📊 Market Ranking", use_container_width=True, key="tab_ranking", 
                       help="View ranked S&P 500 stocks by composite score")
    with tab_col2:
        btn2 = st.button("💼 Portfolio Tracker", use_container_width=True, key="tab_portfolio",
                        help="Track your personal stock portfolio")
    with tab_col3:
        btn3 = st.button("🤖 AI Deep Dive", use_container_width=True, key="tab_ai",
                        help="LLM-powered market analysis")

    # Handle navigation
    if btn1:
        st.session_state["current_page"] = "📊 Market Ranking"
        st.rerun()
    elif btn2:
        st.session_state["current_page"] = "💼 Portfolio Tracker"
        st.rerun()
    elif btn3:
        st.session_state["current_page"] = "🤖 AI Deep Dive"
        st.rerun()

    # Highlight current page with text
    current_page = st.session_state.get("current_page", "📊 Market Ranking")
    st.markdown(f"<div style='text-align:center; color:#666;'>Currently viewing: <strong>{current_page}</strong></div>", 
                unsafe_allow_html=True)
    st.divider()

    # Sidebar with info only (no navigation)
    with st.sidebar:
        st.markdown("---")
        st.caption("Market Analyzer v3")
        st.caption("Portfolio • Live Prices • LLM")
        st.caption("ℹ️ Tips:")
        st.caption("• Prices cached 30 seconds")
        st.caption("• Same tickers combine automatically")
        st.caption("• Dates format: M/D/YY (shares)")

    # Render selected page
    if "📊" in current_page:
        render_market_ranking_page()
    elif "💼" in current_page:
        render_portfolio_page()
    else:
        render_ai_assistant_page()


if __name__ == "__main__":
    main()
