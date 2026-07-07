"""Ranking layer: pure functions that order stock quotes by valuation metrics.
Kept free of I/O so the logic is fast and easy to unit test."""

from __future__ import annotations

from app.data_source import Quote


def rank_by_pe(quotes: list[Quote], limit: int, ascending: bool = True) -> list[Quote]:
    """Return up to `limit` quotes sorted by PE ratio.

    Only quotes with a positive, non-null PE ratio are considered, since a missing or
    non-positive PE (from negative/zero earnings) cannot be meaningfully ranked.
    ascending=True surfaces the lowest-PE (cheapest) names first."""
    valid = [q for q in quotes if q.pe_ratio is not None and q.pe_ratio > 0]
    valid.sort(key=lambda q: q.pe_ratio, reverse=not ascending)
    return valid[:limit]
