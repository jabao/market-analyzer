"""Composite scoring model: blends several metrics into a single 0-100 score so stocks
can be ranked on valuation, profitability, growth, and financial health together rather
than on PE alone. Pure/vectorized (operates on a DataFrame) so it is fast and testable."""

from __future__ import annotations

import pandas as pd

DIMENSIONS = ["valuation", "profitability", "growth", "financial_health"]

DEFAULT_WEIGHTS: dict[str, float] = {
    "valuation": 0.40,
    "profitability": 0.30,
    "growth": 0.20,
    "financial_health": 0.10,
}

METRIC_SPEC: dict[str, list[tuple[str, str]]] = {
    "valuation": [
        ("trailing_pe", "lower"),
        ("forward_pe", "lower"),
        ("peg_ratio", "lower"),
        ("price_to_book", "lower"),
    ],
    "profitability": [
        ("profit_margin", "higher"),
        ("return_on_equity", "higher"),
    ],
    "growth": [
        ("revenue_growth", "higher"),
        ("earnings_growth", "higher"),
    ],
    "financial_health": [
        ("free_cash_flow", "higher"),
        ("debt_to_equity", "lower"),
    ],
}


def normalize_weights(weights: dict[str, float] | None) -> dict[str, float]:
    """Return weights that sum to 1 across the dimensions, defaulting to equal weights
    if none are positive."""
    source = weights or DEFAULT_WEIGHTS
    clean = {dim: max(float(source.get(dim, 0.0)), 0.0) for dim in DIMENSIONS}
    total = sum(clean.values())
    if total <= 0:
        return {dim: 1.0 / len(DIMENSIONS) for dim in DIMENSIONS}
    return {dim: value / total for dim, value in clean.items()}


def score_metrics_frame(frame: pd.DataFrame, weights: dict[str, float] | None = None) -> pd.DataFrame:
    """Score each row of `frame` (columns are Quote metric names) and return a DataFrame
    with `symbol`, one 0-100 sub-score per dimension, and the weighted `composite` score.

    Each metric is converted to a percentile rank within the universe (so metrics on
    different scales are comparable), oriented so higher is always better. Missing metrics
    are skipped; a dimension with no data is dropped and its weight is redistributed across
    the dimensions that do have data for that stock."""
    dim_scores: dict[str, pd.Series] = {}
    for dim, metrics in METRIC_SPEC.items():
        metric_columns = [
            _metric_scores(frame[attr], direction)
            for attr, direction in metrics
            if attr in frame.columns
        ]
        if metric_columns:
            dim_scores[dim] = pd.concat(metric_columns, axis=1).mean(axis=1)
        else:
            dim_scores[dim] = pd.Series(float("nan"), index=frame.index)

    dim_df = pd.DataFrame(dim_scores)[DIMENSIONS]
    weight_series = pd.Series(normalize_weights(weights))
    weighted = dim_df.mul(weight_series, axis=1)
    available_weight = dim_df.notna().mul(weight_series, axis=1).sum(axis=1)
    composite = weighted.sum(axis=1) / available_weight.replace(0, float("nan"))

    result = pd.DataFrame({"symbol": frame["symbol"].values})
    for dim in DIMENSIONS:
        result[dim] = dim_df[dim].values
    result["composite"] = composite.values
    return result


def _metric_scores(series: pd.Series, direction: str) -> pd.Series:
    values = pd.to_numeric(series, errors="coerce")
    if direction == "lower":
        values = values.where(values > 0)
        return (1.0 - values.rank(pct=True)) * 100.0
    return values.rank(pct=True) * 100.0
