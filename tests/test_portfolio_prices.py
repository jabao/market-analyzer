"""Tests for portfolio live prices, with yfinance network access stubbed out."""

import pandas as pd
import pytest

from app import portfolio_service


class FakeTicker:
    infos: dict = {}
    histories: dict = {}
    constructed: list = []

    def __init__(self, symbol):
        self.symbol = symbol
        type(self).constructed.append(symbol)

    @property
    def info(self):
        value = self.infos.get(self.symbol, {})
        if isinstance(value, Exception):
            raise value
        return value

    def history(self, period="5d"):
        value = self.histories.get(self.symbol)
        if isinstance(value, Exception):
            raise value
        if value is None:
            return pd.DataFrame()
        return pd.DataFrame({"Close": value})


@pytest.fixture(autouse=True)
def stub_yfinance(monkeypatch):
    monkeypatch.setattr(portfolio_service.yf, "Ticker", FakeTicker)
    FakeTicker.infos = {}
    FakeTicker.histories = {}
    FakeTicker.constructed = []
    portfolio_service._PRICE_CACHE.clear()
    portfolio_service._FUND_RESOLUTION_CACHE.clear()
    yield
    portfolio_service._PRICE_CACHE.clear()
    portfolio_service._FUND_RESOLUTION_CACHE.clear()


def test_direct_price_from_info():
    FakeTicker.infos = {"AAPL": {"currentPrice": 150.0}}
    assert portfolio_service.get_current_price("AAPL") == 150.0


def test_history_fallback_when_info_empty():
    FakeTicker.infos = {"VIIIX": {}}
    FakeTicker.histories = {"VIIIX": [600.0, 610.0]}
    assert portfolio_service.get_current_price("VIIIX") == 610.0


def test_managed_fund_explicit_mapping():
    FakeTicker.infos = {"SSGA.LG.CAP.GROWTH": {}, "IWF": {"currentPrice": 100.0}}
    assert portfolio_service.get_current_price("SSGA.LG.CAP.GROWTH") == 100.0
    assert "IWF" in FakeTicker.constructed


def test_unresolvable_returns_none(monkeypatch):
    calls = []
    monkeypatch.setattr(
        portfolio_service.data_source,
        "search_symbols",
        lambda *a, **k: calls.append((a, k)) or [],
    )
    assert portfolio_service.get_current_price("NOPE.NOTHING.HERE") is None
    assert calls


def test_search_fallback_resolves_fund(monkeypatch):
    FakeTicker.infos = {"VTTSX": {"regularMarketPrice": 69.5}}
    monkeypatch.setattr(
        portfolio_service.data_source,
        "search_symbols",
        lambda *a, **k: [
            {
                "symbol": "VTTSX",
                "name": "Vanguard Target Retirement 2060 Fund",
                "exchange": "NASDAQ",
                "sector": None,
                "industry": None,
                "quote_type": "MUTUALFUND",
            }
        ],
    )
    assert portfolio_service.get_current_price("FIDELITY.TARGET.2060") == 69.5


def test_resolution_is_cached(monkeypatch):
    calls = []
    FakeTicker.infos = {"VTTSX": {"regularMarketPrice": 69.5}}

    def fake_search(*a, **k):
        calls.append(a)
        return [{"symbol": "VTTSX", "name": "Vanguard Target 2060",
                 "exchange": "NASDAQ", "sector": None, "industry": None,
                 "quote_type": "MUTUALFUND"}]

    monkeypatch.setattr(portfolio_service.data_source, "search_symbols", fake_search)
    assert portfolio_service.get_current_price("FIDELITY.TARGET.2060") == 69.5
    portfolio_service._PRICE_CACHE.clear()
    assert portfolio_service.get_current_price("FIDELITY.TARGET.2060") == 69.5
    assert len(calls) == 1


def test_expand_fund_name():
    assert portfolio_service.expand_fund_name("SSGA.LG.CAP.GROWTH") == "State Street Large Cap Growth"
    assert portfolio_service.expand_fund_name("VANG.INST.500.IDX.TR") == "Vanguard Institutional 500 Index Trust"
    assert portfolio_service.expand_fund_name("VANGUARD.TARGET.2060") == "Vanguard Target 2060"
