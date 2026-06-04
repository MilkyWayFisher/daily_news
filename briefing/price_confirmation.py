from __future__ import annotations

from datetime import datetime, timezone

from briefing.models import MacroIndicator, MarketPoint, PriceConfirmation


def confirm_price_action(
    risk_factor: str,
    primary_assets: list[str],
    market_points: list[MarketPoint],
    macro_indicators: list[MacroIndicator],
) -> PriceConfirmation:
    market = {point.symbol.upper(): point for point in market_points if point.available}
    macro = {indicator.indicator: indicator for indicator in macro_indicators if indicator.available}

    if risk_factor == "oil_supply":
        return _confirm_oil_supply(market)
    if risk_factor == "semiconductors":
        return _confirm_bullish_group(
            ["NVDA", "SMH", "SOXX", "QQQ"],
            market,
            "半导体新闻偏正面，但板块价格确认仍不充分。",
            "半导体和科技相关价格多数上涨，市场对相关叙事有一定确认。",
            "半导体新闻偏正面，但 NVDA / 板块价格偏弱，说明市场仍在消化估值或其他压力。",
        )
    if risk_factor == "rates":
        return _confirm_rates(market, macro)
    if risk_factor in {"geopolitics_war", "trade_policy"}:
        return _confirm_bullish_group(
            ["VIX", "GLD", "DXY"],
            market,
            "政策或地缘风险叙事需要 VIX、黄金或美元进一步确认。",
            "VIX、黄金或美元多数走强，价格表现支持避险叙事。",
            "避险资产表现偏弱，说明市场暂未充分确认该风险。",
        )
    if risk_factor == "company_specific":
        return _confirm_company(primary_assets, market)
    if risk_factor == "musk_ecosystem":
        return PriceConfirmation(
            status="unconfirmed",
            status_zh="价格暂未确认",
            confidence_adjustment="unchanged",
            note=_causality_note("SpaceX 属于私募估值事件，缺少可直接验证的公开价格；TSLA 只适合作为间接情绪指标观察。"),
        )
    if risk_factor == "inflation":
        return _confirm_inflation(market, macro)
    return PriceConfirmation(
        status="unconfirmed",
        status_zh="价格暂未确认",
        confidence_adjustment="unchanged",
        note=_causality_note("该事件没有明确可直接验证的短期价格方向，适合结合后续数据继续观察。"),
    )


def _confirm_bullish_group(
    symbols: list[str],
    market: dict[str, MarketPoint],
    mixed_note: str,
    confirmed_note: str,
    contradicted_note: str,
) -> PriceConfirmation:
    changes = [_change(market.get(symbol)) for symbol in symbols]
    clean = [change for change in changes if change is not None]
    if not clean:
        return _missing_or_stale_confirmation([market.get(symbol) for symbol in symbols], "关键价格数据不足，暂时无法做短期价格同步判断。")
    positives = sum(1 for change in clean if change > 0)
    negatives = sum(1 for change in clean if change < 0)
    if positives >= max(2, negatives + 1):
        return PriceConfirmation("short_price_sync", "短期价格同步", "up", _causality_note(confirmed_note))
    if negatives >= max(2, positives + 1):
        return PriceConfirmation("short_price_divergence", "短期价格背离", "down", _causality_note(contradicted_note))
    return PriceConfirmation("unconfirmed", "价格暂未确认", "unchanged", _causality_note(mixed_note))


def _confirm_oil_supply(market: dict[str, MarketPoint]) -> PriceConfirmation:
    wti = _change(market.get("WTI"))
    uso = _change(market.get("USO"))
    xle = _change(market.get("XLE"))
    clean = [change for change in [wti, uso, xle] if change is not None]
    if not clean:
        return _missing_or_stale_confirmation(
            [market.get("WTI"), market.get("USO"), market.get("XLE")],
            "关键原油和能源价格数据不足，暂时无法做短期价格同步判断。",
        )
    positives = sum(1 for change in clean if change > 0)
    negatives = sum(1 for change in clean if change < 0)
    if wti is not None and wti < 0 and positives >= 1:
        return PriceConfirmation(
            "unconfirmed",
            "价格暂未确认",
            "unchanged",
            _causality_note("新闻叙事偏利好能源，但 WTI 当前下跌，能源资产信号分化，短期价格暂未给出一致同步。"),
        )
    if positives >= max(2, negatives + 1):
        return PriceConfirmation(
            "short_price_sync",
            "短期价格同步",
            "up",
            _causality_note("原油和能源相关资产多数上涨，短期价格与原油供应风险叙事同步。"),
        )
    if negatives >= max(2, positives + 1):
        return PriceConfirmation(
            "short_price_divergence",
            "短期价格背离",
            "down",
            _causality_note("新闻叙事偏利好能源，但 WTI / USO / XLE 多数下跌，短期价格与该叙事背离，可能有其他供需因素抵消。"),
        )
    return PriceConfirmation("unconfirmed", "价格暂未确认", "unchanged", _causality_note("新闻叙事偏利好能源，但关键价格尚未形成一致同步。"))


def _confirm_rates(
    market: dict[str, MarketPoint],
    macro: dict[str, MacroIndicator],
) -> PriceConfirmation:
    y10 = macro.get("10Y Treasury Yield")
    qqq = _change(market.get("QQQ"))
    tlt = _change(market.get("TLT"))
    if y10 is None or y10.latest_value is None or y10.previous_value is None:
        return PriceConfirmation("unavailable", "数据不足", "down", "10Y 美债收益率数据不足，利率压力暂无法做短期价格同步判断。")
    y10_up = y10.latest_value > y10.previous_value
    qqq_down = qqq is not None and qqq < 0
    tlt_down = tlt is not None and tlt < 0
    if y10_up and (qqq_down or tlt_down):
        return PriceConfirmation("short_price_sync", "短期价格同步", "up", _causality_note("10Y 收益率上行，且 QQQ 或 TLT 偏弱，短期价格与利率压力叙事同步。"))
    if y10_up and qqq is not None and qqq > 0:
        return PriceConfirmation("short_price_divergence", "短期价格背离", "down", _causality_note("10Y 收益率上行，但 QQQ 仍上涨，利率压力叙事与风险资产短期价格背离。"))
    return PriceConfirmation("unconfirmed", "价格暂未确认", "unchanged", _causality_note("利率数据存在变化，但风险资产和债券短期价格信号不充分。"))


def _confirm_inflation(
    market: dict[str, MarketPoint],
    macro: dict[str, MacroIndicator],
) -> PriceConfirmation:
    cpi = macro.get("CPI") or macro.get("Core CPI") or macro.get("PCE")
    tlt = _change(market.get("TLT"))
    if cpi is None or cpi.latest_value is None or cpi.previous_value is None:
        return PriceConfirmation("unavailable", "数据不足", "down", "通胀数据不足，暂时无法做短期价格同步判断。")
    if cpi.latest_value > cpi.previous_value and tlt is not None and tlt < 0:
        return PriceConfirmation("short_price_sync", "短期价格同步", "up", _causality_note("通胀数据较前值上行且 TLT 偏弱，短期价格与利率压力叙事同步。"))
    return PriceConfirmation("unconfirmed", "价格暂未确认", "unchanged", _causality_note("通胀数据需要结合债券和美元表现继续观察，短期价格暂未给出一致同步。"))


def _confirm_company(
    primary_assets: list[str],
    market: dict[str, MarketPoint],
) -> PriceConfirmation:
    changes = [_change(market.get(asset.upper())) for asset in primary_assets]
    clean = [change for change in changes if change is not None]
    if not clean:
        return _missing_or_stale_confirmation(
            [market.get(asset.upper()) for asset in primary_assets],
            "相关个股价格数据不足，暂时无法做短期价格同步判断。",
        )
    positives = sum(1 for change in clean if change > 0)
    negatives = sum(1 for change in clean if change < 0)
    if positives > negatives:
        return PriceConfirmation("short_price_sync", "短期价格同步", "up", _causality_note("相关个股价格上涨，短期价格与公司事件方向同步。"))
    if negatives > positives:
        return PriceConfirmation("short_price_divergence", "短期价格背离", "down", _causality_note("相关个股价格偏弱，短期价格与公司事件方向背离。"))
    return PriceConfirmation("unconfirmed", "价格暂未确认", "unchanged", _causality_note("相关个股价格表现分化，仍需继续观察。"))


def _change(point: MarketPoint | None) -> float | None:
    if point is None or not point.available or _is_stale_price(point):
        return None
    return point.daily_change_pct


def _missing_or_stale_confirmation(points: list[MarketPoint | None], missing_note: str) -> PriceConfirmation:
    if any(point is not None and point.available and _is_stale_price(point) for point in points):
        return PriceConfirmation(
            "unconfirmed",
            "价格暂未确认",
            "unchanged",
            _causality_note("当前只有前一交易日或非实时价格，不能强行做短期同步判断。"),
        )
    return PriceConfirmation(
        "unavailable",
        "数据不足",
        "down",
        missing_note,
    )


def _is_stale_price(point: MarketPoint) -> bool:
    raw_date = _raw_market_date(point)
    if raw_date is None:
        return False
    return raw_date < datetime.now(timezone.utc).date()


def _raw_market_date(point: MarketPoint):
    raw = point.raw or {}
    date_value = raw.get("Date")
    if not date_value and isinstance(raw.get("latest"), dict):
        date_value = raw["latest"].get("date")
    if not isinstance(date_value, str) or not date_value:
        return None
    try:
        return datetime.fromisoformat(date_value.strip()).date()
    except ValueError:
        return None


def _causality_note(note: str) -> str:
    suffix = "价格确认只表示短期同步或背离，不代表新闻与价格之间存在因果关系。"
    if suffix in note:
        return note
    return f"{note}{suffix}"
