"""Tests for the service layer, with the data source stubbed out (no network)."""

import pandas as pd

from app import data_source, service
from app.data_source import Quote


def _q(symbol: str, pe: float | None, div: float | None = 0.02) -> Quote:
    return Quote(
        symbol=symbol,
        name=f"{symbol} Inc",
        sector="Tech",
        price=100.0,
        pe_ratio=pe,
        trailing_pe=pe,
        forward_pe=pe,
        peg_ratio=1.5,
        price_to_book=3.0,
        dividend_yield=div,
        beta=1.0,
        market_cap=1e9,
    )


def _patch_source(monkeypatch, quotes):
    monkeypatch.setattr(data_source, "get_sp500_symbols", lambda *a, **k: [q.symbol for q in quotes])
    monkeypatch.setattr(data_source, "get_quotes", lambda *a, **k: quotes)


def test_get_ranked_stocks_orders_and_filters(monkeypatch):
    _patch_source(monkeypatch, [_q("A", 30.0), _q("B", None), _q("C", 10.0)])
    ranked = service.get_ranked_stocks()
    assert [q.symbol for q in ranked] == ["C", "A"]


def test_dataframe_has_display_columns(monkeypatch):
    _patch_source(monkeypatch, [_q("A", 12.0)])
    frame = service.get_ranked_stocks_dataframe()
    assert list(frame.columns) == list(service.DISPLAY_COLUMNS.values())


def test_dividend_yield_passed_through_as_percent(monkeypatch):
    _patch_source(monkeypatch, [_q("A", 12.0, div=2.56)])
    frame = service.get_ranked_stocks_dataframe()
    assert frame["Div Yield %"].iloc[0] == 2.56


def test_empty_universe_returns_empty_frame_with_columns(monkeypatch):
    _patch_source(monkeypatch, [])
    frame = service.get_ranked_stocks_dataframe()
    assert frame.empty
    assert list(frame.columns) == list(service.DISPLAY_COLUMNS.values())


def test_build_scored_dataframe_orders_by_score_and_has_columns():
    quotes = [_q("PRICEY", 30.0), _q("CHEAP", 10.0)]
    base = pd.DataFrame(data_source.quote_to_dict(q) for q in quotes)
    out = service.build_scored_dataframe(base, {"valuation": 1, "profitability": 0,
                                                "growth": 0, "financial_health": 0})
    assert list(out.columns) == service.SCORED_COLUMNS
    assert out.iloc[0]["Ticker"] == "CHEAP"
    assert out.iloc[0]["Score"] >= out.iloc[1]["Score"]


def test_build_scored_dataframe_empty_input():
    out = service.build_scored_dataframe(pd.DataFrame())
    assert out.empty
    assert list(out.columns) == service.SCORED_COLUMNS


def test_get_price_history_shapes_frame(monkeypatch):
    hist = pd.DataFrame(
        {"Open": [9, 10, 11], "Close": [10.0, 11.0, 12.0]},
        index=pd.to_datetime(["2026-01-01", "2026-01-02", "2026-01-03"]),
    )
    hist.index.name = "Date"
    monkeypatch.setattr(service.data_source, "get_price_history", lambda *a, **k: hist)
    out = service.get_price_history("AAPL", "1M")
    assert list(out.columns) == ["Time", "Price"]
    assert len(out) == 3
    assert out["Price"].iloc[-1] == 12.0


def test_get_price_history_empty_when_unavailable(monkeypatch):
    monkeypatch.setattr(service.data_source, "get_price_history", lambda *a, **k: pd.DataFrame())
    out = service.get_price_history("AAPL", "1D")
    assert out.empty
    assert list(out.columns) == ["Time", "Price"]


def test_get_price_history_unknown_range_falls_back(monkeypatch):
    captured = {}

    def fake(symbol, period, interval, **kwargs):
        captured["period"], captured["interval"] = period, interval
        return pd.DataFrame()

    monkeypatch.setattr(service.data_source, "get_price_history", fake)
    service.get_price_history("AAPL", "bogus")
    assert (captured["period"], captured["interval"]) == service.PRICE_RANGES[service.DEFAULT_PRICE_RANGE]


def test_get_stock_details_groups_metrics(monkeypatch):
    info = {
        "shortName": "Apple Inc.",
        "sector": "Technology",
        "trailingPE": 30.0,
        "marketCap": 3e12,
        "profitMargins": 0.25,
        "longBusinessSummary": "Makes phones.",
    }
    monkeypatch.setattr(service.data_source, "get_ticker_info", lambda *a, **k: info)
    details = service.get_stock_details("AAPL")

    assert details["symbol"] == "AAPL"
    assert details["name"] == "Apple Inc."
    assert details["summary"] == "Makes phones."
    section_titles = [title for title, _ in details["sections"]]
    assert "Valuation" in section_titles
    valuation = dict((label, (value, kind)) for section, rows in details["sections"]
                     if section == "Valuation" for label, value, kind in rows)
    assert valuation["Trailing P/E"] == (30.0, "ratio")


def test_get_stock_details_handles_missing_info(monkeypatch):
    monkeypatch.setattr(service.data_source, "get_ticker_info", lambda *a, **k: {})
    details = service.get_stock_details("ZZZ")
    assert details["name"] == "ZZZ"
    assert details["summary"] is None
    for _, rows in details["sections"]:
        for _, value, _ in rows:
            assert value is None
