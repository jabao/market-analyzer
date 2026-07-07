"""Unit tests for the composite scoring model (pure, no network)."""

import math

import pandas as pd

from app import scoring


def _frame(rows: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(rows)


def test_lower_pe_scores_higher_on_valuation():
    frame = _frame([
        {"symbol": "CHEAP", "trailing_pe": 10.0},
        {"symbol": "PRICEY", "trailing_pe": 30.0},
    ])
    scores = scoring.score_metrics_frame(frame).set_index("symbol")
    assert scores.loc["CHEAP", "valuation"] > scores.loc["PRICEY", "valuation"]


def test_non_positive_pe_is_excluded():
    frame = _frame([
        {"symbol": "LOSS", "trailing_pe": -5.0},
        {"symbol": "OK", "trailing_pe": 15.0},
    ])
    scores = scoring.score_metrics_frame(frame).set_index("symbol")
    assert math.isnan(scores.loc["LOSS", "composite"])
    assert not math.isnan(scores.loc["OK", "composite"])


def test_weights_change_ranking_order():
    frame = _frame([
        {"symbol": "A", "trailing_pe": 10.0, "profit_margin": 0.10},
        {"symbol": "B", "trailing_pe": 30.0, "profit_margin": 0.40},
    ])
    value_first = scoring.score_metrics_frame(
        frame, {"valuation": 1, "profitability": 0, "growth": 0, "financial_health": 0}
    ).set_index("symbol")
    profit_first = scoring.score_metrics_frame(
        frame, {"valuation": 0, "profitability": 1, "growth": 0, "financial_health": 0}
    ).set_index("symbol")

    assert value_first.loc["A", "composite"] > value_first.loc["B", "composite"]
    assert profit_first.loc["B", "composite"] > profit_first.loc["A", "composite"]


def test_normalize_weights_sums_to_one():
    normalized = scoring.normalize_weights({"valuation": 40, "profitability": 30,
                                            "growth": 20, "financial_health": 10})
    assert round(sum(normalized.values()), 6) == 1.0
    assert normalized["valuation"] == 0.4


def test_normalize_weights_all_zero_falls_back_to_equal():
    normalized = scoring.normalize_weights({d: 0 for d in scoring.DIMENSIONS})
    assert all(round(v, 6) == 0.25 for v in normalized.values())
