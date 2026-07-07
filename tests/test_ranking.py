"""Unit tests for the pure ranking logic (no network access)."""

from app.data_source import Quote
from app.ranking import rank_by_pe


def _q(symbol: str, pe: float | None) -> Quote:
    return Quote(
        symbol=symbol,
        name=symbol,
        sector="Tech",
        price=100.0,
        pe_ratio=pe,
        trailing_pe=pe,
        forward_pe=pe,
        peg_ratio=1.0,
        price_to_book=2.0,
        dividend_yield=0.01,
        beta=1.1,
        market_cap=1e9,
    )


def test_ranks_ascending_by_pe():
    quotes = [_q("A", 30.0), _q("B", 10.0), _q("C", 20.0)]
    ranked = rank_by_pe(quotes, limit=3)
    assert [q.symbol for q in ranked] == ["B", "C", "A"]


def test_respects_limit():
    quotes = [_q("A", 30.0), _q("B", 10.0), _q("C", 20.0)]
    ranked = rank_by_pe(quotes, limit=2)
    assert [q.symbol for q in ranked] == ["B", "C"]


def test_descending_order():
    quotes = [_q("A", 30.0), _q("B", 10.0), _q("C", 20.0)]
    ranked = rank_by_pe(quotes, limit=3, ascending=False)
    assert [q.symbol for q in ranked] == ["A", "C", "B"]


def test_excludes_missing_and_nonpositive_pe():
    quotes = [_q("A", None), _q("B", -5.0), _q("C", 0.0), _q("D", 15.0)]
    ranked = rank_by_pe(quotes, limit=10)
    assert [q.symbol for q in ranked] == ["D"]
