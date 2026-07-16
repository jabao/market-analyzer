"""Market context builder: turns live S&P 500 data into prompt-ready strings.

Uses app.service and app.data_source to produce:
- top stocks summary
- sector summary (avg score, valuation, etc.)
- fundamentals per ticker
- broad market stats

Pure functions where possible for testability; network calls isolated and cached.
"""

from __future__ import annotations

import json
import statistics
from datetime import datetime
from typing import List

import pandas as pd

from app import data_source, scoring, service


def get_current_date_str() -> str:
    return datetime.now().strftime("%Y-%m-%d (%A)")


def format_top_stocks(
    scored_df: pd.DataFrame,
    top_n: int = 20,
) -> str:
    """Format top N scored rows as compact table for prompt injection."""
    if scored_df is None or scored_df.empty:
        return "No scored data available (fetch failed)."

    subset = scored_df.head(top_n)
    lines = []
    lines.append(
        f"{'Rank':<4} {'Ticker':<6} {'Company':<25} {'Score':<6} {'Val':<5} {'Prof':<5} {'Grow':<5} {'Health':<6} {'Sector':<20} {'P/E':<6} {'Fwd P/E':<7} {'PEG':<5} {'P/B':<5} {'Beta':<5}"
    )
    lines.append("-" * 150)
    for i, row in enumerate(subset.itertuples(), start=1):
        try:
            company = str(getattr(row, "Company", ""))[:24]
            sector = str(getattr(row, "Sector", ""))[:19]
            ticker = getattr(row, "Ticker", "")
            score = getattr(row, "Score", 0) or 0
            val = getattr(row, "Valuation", 0) or 0
            prof = getattr(row, "Profitability", 0) or 0
            grow = getattr(row, "Growth", 0) or 0
            health = getattr(row, "Health", 0) or 0
            pe = getattr(row, getattr(row, "_fields", [""])[8] if hasattr(row, "_fields") else "Trailing P/E", None) if False else None
            # Use _asdict style fallback: access via dict
            # Since itertuples may mangle column names, use getattr with space names fallback via index
            # Safer: use DataFrame row
        except Exception:
            pass

    # More robust: iterate DataFrame rows
    lines = []
    header = "Rank | Ticker | Company | Score | Val | Prof | Growth | Health | Sector | Price | T/PE | FwdPE | PEG | P/B | Beta | MktCap"
    lines.append(header)
    lines.append("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for idx, row in subset.iterrows():
        try:
            rank = idx + 1
            lines.append(
                f"{rank} | {row.get('Ticker','')} | {str(row.get('Company',''))[:30]} | {row.get('Score',0):.1f} | "
                f"{row.get('Valuation',0):.1f} | {row.get('Profitability',0):.1f} | {row.get('Growth',0):.1f} | {row.get('Health',0):.1f} | "
                f"{row.get('Sector','')} | ${row.get('Price',0):.2f} | {row.get('Trailing P/E','-')} | {row.get('Forward P/E','-')} | "
                f"{row.get('PEG','-')} | {row.get('P/B','-')} | {row.get('Beta','-')} | {row.get('Market Cap','-')}"
            )
        except Exception as e:
            lines.append(f"{idx} | parse error: {e}")
    return "\n".join(lines)


def format_sector_summary(
    scored_df: pd.DataFrame,
    raw_quotes_df: pd.DataFrame | None = None,
) -> str:
    """Aggregate by sector: avg score, avg valuation metrics, count.

    If raw_quotes_df provided, can compute additional metrics, but scored_df alone suffices.
    """
    if scored_df is None or scored_df.empty:
        return "No sector data available."

    try:
        grouped = scored_df.groupby("Sector").agg(
            Count=("Ticker", "count"),
            AvgScore=("Score", "mean"),
            AvgVal=("Valuation", "mean"),
            AvgProf=("Profitability", "mean"),
            AvgGrowth=("Growth", "mean"),
            AvgHealth=("Health", "mean"),
            AvgPE=("Trailing P/E", "mean"),
            AvgFwdPE=("Forward P/E", "mean"),
            AvgBeta=("Beta", "mean"),
        ).sort_values("AvgScore", ascending=False)

        lines = []
        lines.append("Sector | Count | AvgScore | AvgVal | AvgProf | AvgGrowth | AvgHealth | Avg trailing P/E | Avg Fwd P/E | Avg Beta")
        lines.append("|---|---|---|---|---|---|---|---|---|---|")
        for sector, row in grouped.iterrows():
            lines.append(
                f"{sector} | {int(row['Count'])} | {row['AvgScore']:.1f} | {row['AvgVal']:.1f} | {row['AvgProf']:.1f} | "
                f"{row['AvgGrowth']:.1f} | {row['AvgHealth']:.1f} | {row['AvgPE']:.2f} | {row['AvgFwdPE']:.2f} | {row['AvgBeta']:.2f}"
            )
        # Top 3 tickers per sector by score
        lines.append("\nTop 3 per sector by composite score:")
        for sector in grouped.index[:]:
            top_in_sector = scored_df[scored_df["Sector"] == sector].head(3)
            tickers = ", ".join([f"{r['Ticker']}({r['Score']:.0f})" for _, r in top_in_sector.iterrows()])
            lines.append(f"- {sector}: {tickers}")

        return "\n".join(lines)
    except Exception as e:
        return f"Failed to build sector summary: {e}. Raw columns: {list(scored_df.columns)}"


def format_market_stats(scored_df: pd.DataFrame) -> str:
    """Broad market stats for prompt."""
    if scored_df is None or scored_df.empty:
        return "No market stats."
    try:
        stats_lines = []
        stats_lines.append(f"Total stocks scored: {len(scored_df)}")
        stats_lines.append(f"Avg composite Score: {scored_df['Score'].mean():.1f} (median {scored_df['Score'].median():.1f}, stdev {scored_df['Score'].std():.1f})")
        # PE stats
        pe_valid = pd.to_numeric(scored_df["Trailing P/E"], errors="coerce").dropna()
        if not pe_valid.empty:
            pe_valid = pe_valid[pe_valid > 0]
            stats_lines.append(f"Avg Trailing P/E: {pe_valid.mean():.2f} (median {pe_valid.median():.2f}, 10th pct {pe_valid.quantile(0.1):.2f}, 90th pct {pe_valid.quantile(0.9):.2f})")
        fwd_valid = pd.to_numeric(scored_df["Forward P/E"], errors="coerce").dropna()
        if not fwd_valid.empty:
            fwd_valid = fwd_valid[fwd_valid > 0]
            stats_lines.append(f"Avg Forward P/E: {fwd_valid.mean():.2f} (median {fwd_valid.median():.2f})")
        # Score distribution
        top_10_avg = scored_df.head(10)["Score"].mean()
        bottom_10_avg = scored_df.tail(10)["Score"].mean()
        stats_lines.append(f"Top 10 avg score: {top_10_avg:.1f}, Bottom 10 avg score: {bottom_10_avg:.1f}")
        # Sector leaders
        if "Sector" in scored_df.columns:
            sector_counts = scored_df.head(50)["Sector"].value_counts().head(3)
            stats_lines.append(f"Most represented in top 50: {', '.join([f'{k}({v})' for k,v in sector_counts.items()])}")
        return "\n".join(stats_lines)
    except Exception as e:
        return f"Stats error: {e}"


def format_fundamentals(tickers: List[str], max_tickers: int = 10) -> str:
    """Fetch detailed fundamentals for tickers via service.get_stock_details.

    Limited to max_tickers to avoid prompt blow-up and rate limits.
    """
    if not tickers:
        return "No tickers provided."

    tickers = [t.strip().upper() for t in tickers if t.strip()][:max_tickers]
    sections_out = []
    for ticker in tickers:
        try:
            details = service.get_stock_details(ticker)
            if not details.get("found"):
                sections_out.append(f"\n=== {ticker}: NOT FOUND ===")
                continue
            sections_out.append(f"\n=== {ticker} - {details.get('name','')} ===")
            if details.get("summary"):
                # Truncate summary
                summary = details["summary"][:500]
                sections_out.append(f"Summary: {summary}...")
            for sec_title, rows in details["sections"]:
                sections_out.append(f"\n-- {sec_title} --")
                for label, value, kind in rows:
                    if value is None:
                        continue
                    # Format some values nicely
                    if kind == "price" and isinstance(value, (int, float)):
                        sections_out.append(f"{label}: ${value:.2f}")
                    elif kind == "percent" and isinstance(value, (int, float)):
                        sections_out.append(f"{label}: {value*100:.2f}%")
                    elif kind == "large" and isinstance(value, (int, float)):
                        # Convert to readable
                        if abs(value) >= 1e12:
                            sections_out.append(f"{label}: ${value/1e12:.2f}T")
                        elif abs(value) >= 1e9:
                            sections_out.append(f"{label}: ${value/1e9:.2f}B")
                        else:
                            sections_out.append(f"{label}: {value}")
                    else:
                        sections_out.append(f"{label}: {value}")
        except Exception as e:
            sections_out.append(f"\n=== {ticker}: error fetching - {e} ===")

    return "\n".join(sections_out) if sections_out else "No fundamentals obtained."


def build_full_context(
    tickers_for_fundamentals: List[str] | None = None,
    top_n: int = 20,
    weights: dict | None = None,
) -> dict:
    """Build a dict with all context strings ready for prompt injection.

    This does network calls; caller should cache via Streamlit cache_data.
    """
    # Fetch quotes dataframe (cached 15 min inside service if called via wrapper, but here direct)
    try:
        quotes_df = service.get_quotes_dataframe()
    except Exception:
        quotes_df = pd.DataFrame()

    try:
        scored_df = service.build_scored_dataframe(quotes_df, weights)
    except Exception:
        scored_df = pd.DataFrame()

    top_stocks_str = format_top_stocks(scored_df, top_n=top_n)
    sector_summary_str = format_sector_summary(scored_df, quotes_df)
    market_stats_str = format_market_stats(scored_df)

    fundamentals_str = "No specific tickers requested for deep fundamentals."
    if tickers_for_fundamentals:
        fundamentals_str = format_fundamentals(tickers_for_fundamentals)

    valuation_context = _build_valuation_context(scored_df)

    return {
        "quotes_df": quotes_df,
        "scored_df": scored_df,
        "top_stocks": top_stocks_str,
        "sector_summary": sector_summary_str,
        "market_stats": market_stats_str,
        "fundamentals": fundamentals_str,
        "valuation_context": valuation_context,
        "date": get_current_date_str(),
    }


def _build_valuation_context(scored_df: pd.DataFrame) -> str:
    """Provide additional valuation percentile context."""
    if scored_df is None or scored_df.empty:
        return "No valuation context."
    try:
        lines = ["Valuation percentiles across S&P 500 (as of snapshot):"]
        for col in ["Trailing P/E", "Forward P/E", "PEG", "P/B", "Div Yield %"]:
            if col not in scored_df.columns:
                continue
            series = pd.to_numeric(scored_df[col], errors="coerce").dropna()
            if series.empty:
                continue
            if "Div Yield" in col:
                # Higher yield is often value signal, keep as is
                pass
            else:
                series = series[series > 0]
            lines.append(
                f"- {col}: mean {series.mean():.2f}, median {series.median():.2f}, "
                f"25th {series.quantile(0.25):.2f}, 75th {series.quantile(0.75):.2f}, "
                f"10th {series.quantile(0.10):.2f}, 90th {series.quantile(0.90):.2f}"
            )
        return "\n".join(lines)
    except Exception as e:
        return f"Valuation context error: {e}"
