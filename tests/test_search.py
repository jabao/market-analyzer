"""Tests for universal stock search, with Yahoo Finance network access stubbed out."""

import pytest

from app import data_source


QUOTES = [
    {"symbol": "AAPL", "longname": "Apple Inc.", "shortname": "Apple",
     "exchDisp": "NASDAQ", "exchange": "NMS", "sector": "Technology",
     "industry": "Consumer Electronics", "quoteType": "EQUITY"},
    {"symbol": "APLE", "longname": "Apple Hospitality REIT, Inc.", "shortname": "Apple REIT",
     "exchDisp": "NYSE", "exchange": "NYQ", "sector": "Real Estate",
     "industry": "REIT", "quoteType": "EQUITY"},
    {"symbol": "SPY", "longname": "SPDR S&P 500 ETF", "shortname": "SPDR",
     "exchDisp": "NYSEArca", "exchange": "PCX", "sector": None,
     "industry": None, "quoteType": "ETF"},
    {"symbol": "AAPL.FUND", "longname": "Some Fund", "shortname": "Fund",
     "exchDisp": "NASDAQ", "exchange": "NMS", "sector": None,
     "industry": None, "quoteType": "MUTUALFUND"},
    {"symbol": "", "longname": "No Symbol", "shortname": "No Symbol",
     "exchDisp": "NASDAQ", "exchange": "NMS", "sector": None,
     "industry": None, "quoteType": "EQUITY"},
]


@pytest.fixture(autouse=True)
def clear_search_cache():
    data_source._search_cache.clear()
    yield
    data_source._search_cache.clear()


def _patch_search(monkeypatch, quotes, fail=False):
    import yfinance.search as yf_search

    created = {"calls": 0}

    class FakeSearch:
        def __init__(self, query, **kwargs):
            created["calls"] += 1
            created["query"] = query
            if fail:
                raise RuntimeError("network down")
            self._quotes = quotes

        @property
        def quotes(self):
            return self._quotes

    monkeypatch.setattr(yf_search, "Search", FakeSearch)
    return created


def test_search_returns_only_stocks_and_etfs(monkeypatch):
    _patch_search(monkeypatch, QUOTES)
    results = data_source.search_symbols("apple")
    assert [r["symbol"] for r in results] == ["AAPL", "APLE", "SPY"]
    first = results[0]
    assert first["name"] == "Apple Inc."
    assert first["exchange"] == "NASDAQ"
    assert first["sector"] == "Technology"
    assert first["quote_type"] == "EQUITY"


def test_search_blank_query_skips_network(monkeypatch):
    created = _patch_search(monkeypatch, QUOTES)
    assert data_source.search_symbols("   ") == []
    assert created["calls"] == 0


def test_search_failure_returns_empty(monkeypatch):
    _patch_search(monkeypatch, QUOTES, fail=True)
    assert data_source.search_symbols("apple") == []


def test_search_results_are_cached(monkeypatch):
    created = _patch_search(monkeypatch, QUOTES)
    first = data_source.search_symbols("apple")
    second = data_source.search_symbols("APPLE")
    assert created["calls"] == 1
    assert first == second


def test_search_limit_caps_results(monkeypatch):
    _patch_search(monkeypatch, QUOTES)
    results = data_source.search_symbols("apple", max_results=2)
    assert len(results) == 2


def test_search_exact_ticker_ranked_first(monkeypatch):
    _patch_search(monkeypatch, QUOTES)
    results = data_source.search_symbols("aple")
    assert results[0]["symbol"] == "APLE"


def test_search_symbol_prefix_beats_name_match(monkeypatch):
    quotes = [
        {"symbol": "XYZ", "longname": "GameStop Corp.", "shortname": "GameStop",
         "exchDisp": "NYSE", "exchange": "NYQ", "sector": None,
         "industry": None, "quoteType": "EQUITY"},
        {"symbol": "GAME", "longname": "Engine Gaming Inc.", "shortname": "Engine",
         "exchDisp": "NASDAQ", "exchange": "NMS", "sector": None,
         "industry": None, "quoteType": "EQUITY"},
    ]
    _patch_search(monkeypatch, quotes)
    results = data_source.search_symbols("game")
    assert [r["symbol"] for r in results] == ["GAME", "XYZ"]


def test_search_name_match_beats_unrelated(monkeypatch):
    quotes = [
        {"symbol": "ZZZ", "longname": "Zed Zed Corp.", "shortname": "Zed",
         "exchDisp": "NYSE", "exchange": "NYQ", "sector": None,
         "industry": None, "quoteType": "EQUITY"},
        {"symbol": "GME", "longname": "GameStop Corp.", "shortname": "GameStop",
         "exchDisp": "NYSE", "exchange": "NYQ", "sector": "Consumer Cyclical",
         "industry": "Specialty Retail", "quoteType": "EQUITY"},
    ]
    _patch_search(monkeypatch, quotes)
    results = data_source.search_symbols("gamestop")
    assert results[0]["symbol"] == "GME"
