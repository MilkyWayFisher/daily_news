from __future__ import annotations

from datetime import date, datetime, timedelta, timezone


RISK_FACTOR_ZH = {
    "oil_supply": "原油供应",
    "semiconductors": "半导体",
    "company_specific": "公司事件",
    "trade_policy": "贸易政策",
    "rates": "利率",
    "inflation": "通胀",
    "fed_policy": "美联储政策",
    "geopolitics_war": "地缘冲突",
    "tariffs": "关税",
    "ai_capex": "AI 资本开支",
    "earnings": "财报",
    "soft_commodities": "软商品",
    "musk_ecosystem": "Elon Musk 关联生态 / 私募估值",
    "low_relevance": "低相关",
}

CATEGORY_ZH = {
    "macro": "宏观经济",
    "market": "市场价格",
    "geopolitics": "地缘政治",
    "company": "公司新闻",
    "sector": "行业新闻",
    "earnings": "财报",
    "policy": "政策监管",
    "commodity": "商品 / 能源",
    "rates": "利率",
    "low_relevance": "低相关",
}

SCORE_BUCKET_ZH = {
    "core": "L1 核心事件",
    "important": "L2 重点事件",
    "watch": "L3 观察事件",
    "background": "背景信息",
    "noise": "背景信息",
}

DIRECTION_ZH = {
    "bullish": "偏利好",
    "bearish": "偏利空",
    "mixed": "影响复杂",
    "unclear": "方向不明确",
}

STRENGTH_ZH = {"high": "高", "medium": "中", "low": "低"}
CONFIDENCE_ZH = {"high": "高", "medium": "中", "low": "低"}

WATCH_ITEM_ZH = {
    "10Y yield": "10Y 美债收益率",
    "2Y yield": "2Y 美债收益率",
    "real yields": "实际利率",
    "DXY": "DXY",
    "VIX": "VIX",
    "QQQ/SPY relative performance": "QQQ / SPY 相对表现",
    "WTI": "WTI",
    "Brent": "Brent",
    "USO": "USO",
    "XLE": "XLE",
    "inflation breakevens": "通胀盈亏平衡预期",
    "SMH": "SMH",
    "SOXX": "SOXX",
    "NVDA": "NVDA",
    "AMD": "AMD",
    "AVGO": "AVGO",
    "AI capex commentary": "AI 资本开支评论",
    "QQQ": "QQQ",
    "CPI/PCE details": "CPI / PCE 细项",
    "AAPL": "AAPL",
    "MSFT": "MSFT",
    "earnings commentary": "盈利与指引评论",
    "relative performance": "相对表现",
    "gold": "黄金",
    "oil": "原油",
    "shipping rates": "航运价格",
    "policy details": "政策细节",
    "affected goods": "受影响商品",
    "CPI pass-through": "CPI 传导",
    "affected companies": "受影响公司",
    "TSLA relative to QQQ/SPY": "TSLA 相对 QQQ / SPY 表现",
    "SpaceX valuation comps": "SpaceX 私募估值可比交易",
    "private market liquidity": "私募市场流动性",
}


def risk_factor_zh(value: str) -> str:
    return RISK_FACTOR_ZH.get(value, "其他风险因子")


def category_zh(value: str) -> str:
    return CATEGORY_ZH.get(value, "其他事件")


def score_bucket_zh(value: str) -> str:
    return SCORE_BUCKET_ZH.get(value, "观察事件")


def direction_zh(value: str) -> str:
    return DIRECTION_ZH.get(value, "方向不明确")


def strength_zh(value: str) -> str:
    return STRENGTH_ZH.get(value, "中")


def confidence_zh(value: str) -> str:
    return CONFIDENCE_ZH.get(value, "中")


def watch_item_zh(value: str) -> str:
    return WATCH_ITEM_ZH.get(value, value)


def format_local_time(value: str) -> str:
    parsed = _parse_datetime(value)
    if parsed is None:
        return value or "时间未知"
    local_dt, label = to_central(parsed)
    return f"{local_dt.strftime('%Y-%m-%d %H:%M')} {label}"


def data_window_for(run_date: str) -> tuple[str, str, str]:
    try:
        day = date.fromisoformat(run_date)
    except ValueError:
        day = datetime.now(timezone.utc).date()
    end_utc = datetime.now(timezone.utc)
    start_utc = end_utc - timedelta(hours=24)
    start_local, label = to_central(start_utc)
    end_local, _ = to_central(end_utc)
    if end_local.date() != day and day <= end_utc.date():
        return start_local.strftime("%Y-%m-%d %H:%M"), end_local.strftime("%Y-%m-%d %H:%M"), label
    return start_local.strftime("%Y-%m-%d %H:%M"), end_local.strftime("%Y-%m-%d %H:%M"), label


def format_data_window(start_value: str, end_value: str, fallback_date: str) -> tuple[str, str, str]:
    start = _parse_datetime(start_value)
    end = _parse_datetime(end_value)
    if start is None or end is None or start >= end:
        return data_window_for(fallback_date)
    start_local, label = to_central(start)
    end_local, _ = to_central(end)
    return start_local.strftime("%Y-%m-%d %H:%M"), end_local.strftime("%Y-%m-%d %H:%M"), label


def to_central(value: datetime) -> tuple[datetime, str]:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    utc_value = value.astimezone(timezone.utc)
    label = "CDT" if _is_central_daylight_time(utc_value.date()) else "CST"
    offset_hours = -5 if label == "CDT" else -6
    return (utc_value + timedelta(hours=offset_hours)).replace(tzinfo=None), label


def _parse_datetime(value: str) -> datetime | None:
    if not value:
        return None
    cleaned = value.strip()
    if cleaned.endswith("Z"):
        cleaned = cleaned[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(cleaned)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _is_central_daylight_time(day: date) -> bool:
    start = _nth_weekday(day.year, 3, 6, 2)
    end = _nth_weekday(day.year, 11, 6, 1)
    return start <= day < end


def _nth_weekday(year: int, month: int, weekday: int, nth: int) -> date:
    first = date(year, month, 1)
    days_until = (weekday - first.weekday()) % 7
    return first + timedelta(days=days_until + (nth - 1) * 7)
