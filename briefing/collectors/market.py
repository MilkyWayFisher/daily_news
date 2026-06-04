from __future__ import annotations

import csv
from datetime import datetime, timezone
from io import StringIO
import time
import urllib.error
import urllib.request

from briefing.collectors.base import MarketCollector
from briefing.env import first_env
from briefing.http import HttpError, get_json
from briefing.models import MarketPoint


MARKET_NAMES: dict[str, str] = {
    "VOO": "Vanguard S&P 500 ETF",
    "SPY": "SPDR S&P 500 ETF",
    "QQQ": "Invesco QQQ Trust",
    "NVDA": "Nvidia",
    "AAPL": "Apple",
    "MSFT": "Microsoft",
    "TSLA": "Tesla",
    "TLT": "iShares 20+ Year Treasury Bond ETF",
    "GLD": "SPDR Gold Shares",
    "XLE": "Energy Select Sector SPDR Fund",
    "USO": "United States Oil Fund",
    "VIX": "CBOE Volatility Index",
    "DXY": "US Dollar Index",
    "WTI": "WTI Crude Oil",
    "GOLD": "Gold",
}

STOOQ_SYMBOLS: dict[str, str] = {
    "VOO": "voo.us",
    "SPY": "spy.us",
    "QQQ": "qqq.us",
    "NVDA": "nvda.us",
    "AAPL": "aapl.us",
    "MSFT": "msft.us",
    "TSLA": "tsla.us",
    "TLT": "tlt.us",
    "GLD": "gld.us",
    "XLE": "xle.us",
    "USO": "uso.us",
}

FRED_MARKET_SERIES: dict[str, str] = {
    "VIX": "VIXCLS",
    "DXY": "DTWEXBGS",
    "WTI": "DCOILWTICO",
    "GOLD": "GOLDAMGBD228NLBM",
}


class AlphaVantageMarketCollector(MarketCollector):
    provider_name = "alphavantage_market"
    endpoint = "https://www.alphavantage.co/query"

    def collect(self, symbols: list[str]) -> list[MarketPoint]:
        api_key = first_env("ALPHAVANTAGE_API_KEY", "ALPHAVANTAGE_KEY")
        points: list[MarketPoint] = []
        rate_limited = False

        for symbol in symbols[:20]:
            point: MarketPoint | None = None
            av_note = ""
            if api_key and not rate_limited:
                point, av_note = self._collect_alpha_vantage(symbol, api_key)
                if av_note:
                    rate_limited = True
            if point is None:
                point = _collect_fred_market(symbol)
            if point is None:
                point = _collect_stooq(symbol)
            if point is None:
                reason = av_note or "主数据源和 fallback 均未返回该指标"
                point = _unavailable_point(symbol, reason)
            points.append(point)
        return points

    def _collect_alpha_vantage(self, symbol: str, api_key: str) -> tuple[MarketPoint | None, str]:
        params = {"function": "GLOBAL_QUOTE", "symbol": symbol, "apikey": api_key}
        try:
            data = get_json(self.endpoint, params=params, timeout=15)
        except HttpError as exc:
            return None, f"Alpha Vantage 请求失败：{exc}"

        note = data.get("Note") or data.get("Information") or data.get("Error Message") or ""
        quote = data.get("Global Quote", {}) or {}
        value = _parse_float(quote.get("05. price"))
        change_percent = _parse_percent(quote.get("10. change percent"))
        if value is None and change_percent is None:
            return None, str(note)

        return (
            MarketPoint(
                symbol=symbol,
                name=MARKET_NAMES.get(symbol, symbol),
                value=value,
                change_percent=change_percent,
                timestamp=datetime.now(timezone.utc).isoformat(timespec="seconds"),
                source="Alpha Vantage",
                raw=quote,
            ),
            "",
        )


def _collect_stooq(symbol: str) -> MarketPoint | None:
    stooq_symbol = STOOQ_SYMBOLS.get(symbol.upper())
    if not stooq_symbol:
        return None
    url = f"https://stooq.com/q/l/?s={stooq_symbol}&f=sd2t2ohlcv&h&e=csv"
    try:
        request = urllib.request.Request(url, headers={"User-Agent": "daily-investment-brief/1.0"})
        with urllib.request.urlopen(request, timeout=15) as response:
            payload = response.read().decode("utf-8")
    except (urllib.error.URLError, TimeoutError, OSError):
        return None

    rows = list(csv.DictReader(StringIO(payload)))
    if not rows:
        return None
    row = rows[0]
    close = _parse_float(row.get("Close"))
    open_price = _parse_float(row.get("Open"))
    if close is None:
        return None
    change_percent = None
    if open_price not in (None, 0):
        change_percent = ((close - open_price) / open_price) * 100
    return MarketPoint(
        symbol=symbol,
        name=MARKET_NAMES.get(symbol, symbol),
        value=close,
        change_percent=change_percent,
        timestamp=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        source="Stooq fallback",
        raw=row,
    )


def _collect_fred_market(symbol: str) -> MarketPoint | None:
    series_id = FRED_MARKET_SERIES.get(symbol.upper())
    api_key = first_env("FRED_API_KEY")
    if not series_id or not api_key:
        return None
    time.sleep(0.4)
    params = {
        "series_id": series_id,
        "api_key": api_key,
        "file_type": "json",
        "sort_order": "desc",
        "limit": 5,
    }
    try:
        data = get_json("https://api.stlouisfed.org/fred/series/observations", params=params, timeout=20)
    except HttpError:
        return None
    observations = [
        item for item in data.get("observations", []) or [] if item.get("value") not in {None, "."}
    ]
    if not observations:
        return None
    latest = observations[0]
    previous = observations[1] if len(observations) > 1 else {}
    value = _parse_float(latest.get("value"))
    previous_value = _parse_float(previous.get("value"))
    if value is None:
        return None
    change_percent = None
    if previous_value not in (None, 0):
        change_percent = ((value - previous_value) / previous_value) * 100
    return MarketPoint(
        symbol=symbol,
        name=MARKET_NAMES.get(symbol, symbol),
        value=value,
        change_percent=change_percent,
        timestamp=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        source="FRED fallback",
        raw={"series_id": series_id, "latest": latest, "previous": previous},
    )


def _unavailable_point(symbol: str, reason: str) -> MarketPoint:
    return MarketPoint(
        symbol=symbol,
        name=MARKET_NAMES.get(symbol, symbol),
        source="unavailable",
        updated_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        available=False,
        note=reason,
        raw={"reason": reason},
    )


def _parse_float(value: str | None) -> float | None:
    if value in (None, "", "N/D"):
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _parse_percent(value: str | None) -> float | None:
    if value in (None, ""):
        return None
    cleaned = value.strip().rstrip("%")
    try:
        return float(cleaned)
    except ValueError:
        return None
