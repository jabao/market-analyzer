"""Streamlit dashboard for browsing S&P 500 stocks ranked by a composite valuation score.
Run with:
    streamlit run dashboard.py

The composite score blends valuation, profitability, growth, and financial-health metrics
into a single 0-100 number; the dimension weights are adjustable in the sidebar. Uses an
AgGrid data grid so users can click any column header to sort ascending/descending across
the full dataset, choose 10/20/50 rows per page, and paginate. Click a row — or search any
ticker — to see a full metric breakdown."""

from __future__ import annotations

import math

import pandas as pd
import streamlit as st
from st_aggrid import AgGrid, GridOptionsBuilder, GridUpdateMode, JsCode

from app import scoring
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


def _formatter(expression: str) -> JsCode:
    return JsCode(f"function(params) {{ return params.value == null ? '' : {expression}; }}")


@st.cache_data(ttl=15 * 60, show_spinner="Fetching S&P 500 market data…")
def load_quotes() -> pd.DataFrame:
    """Load the raw S&P 500 quotes table (the network-bound step), cached for 15 minutes.

    Scoring is applied on top of this cheaply, so changing weights re-ranks instantly
    without refetching."""
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
    """Format a raw metric value for display according to its kind."""
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
    """Format a large number with a T/B/M/K suffix, optionally as a dollar amount."""
    prefix = "$" if currency else ""
    for suffix, threshold in (("T", 1e12), ("B", 1e9), ("M", 1e6), ("K", 1e3)):
        if abs(value) >= threshold:
            return f"{prefix}{value / threshold:,.2f}{suffix}"
    return f"{prefix}{value:,.0f}"


def render_price_chart(symbol: str) -> None:
    """Render a closing-price line chart with a selectable time range for one ticker."""
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
    """Render the full grouped metric overview for a single ticker, or warn if unknown."""
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
    """Extract the ticker of the selected row from an AgGrid response, if any."""
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
    """Render the composite-score weight sliders and return the chosen weights."""
    st.subheader("Composite score weights")
    st.caption("Relative importance of each dimension. Values are normalized automatically.")
    weights: dict[str, float] = {}
    for dim in scoring.DIMENSIONS:
        default = int(scoring.DEFAULT_WEIGHTS[dim] * 100)
        weights[dim] = st.slider(WEIGHT_LABELS[dim], min_value=0, max_value=100, value=default, step=5)
    return weights


def main() -> None:
    st.set_page_config(page_title="Market Analyzer — Composite Ranking", layout="wide")
    st.title("📊 Market Analyzer")
    st.caption("S&P 500 stocks ranked by a composite valuation score (higher = better). "
               "Tune the dimension weights in the sidebar; click a column header to sort.")

    with st.sidebar:
        st.header("Options")
        page_size = st.selectbox("Rows per page", PAGE_SIZES, index=0)
        if st.button("🔄 Refresh data"):
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
        "Search any ticker", placeholder="e.g. NVDA, TSLA — or click a row above"
    ).strip().upper()

    symbol = search or selected_symbol(grid_response)
    if symbol:
        render_details(symbol)
    else:
        st.info("👆 Click any row above, or search a ticker, to see a full metric breakdown.")


if __name__ == "__main__":
    main()
