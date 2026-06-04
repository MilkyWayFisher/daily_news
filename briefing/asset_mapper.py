from __future__ import annotations

import re

from briefing.config import AppConfig
from briefing.models import AssetImpact, NewsItem


COMPANY_ASSETS: dict[str, str] = {
    "nvidia": "NVDA",
    "nvda": "NVDA",
    "marvell": "MRVL",
    "mrvl": "MRVL",
    "amd": "AMD",
    "broadcom": "AVGO",
    "avgo": "AVGO",
    "apple": "AAPL",
    "aapl": "AAPL",
    "microsoft": "MSFT",
    "msft": "MSFT",
    "tesla": "TSLA",
    "tsla": "TSLA",
}

RISK_RULES: list[dict[str, object]] = [
    {
        "risk_factor": "rates",
        "keywords": ("treasury yield", "treasury yields", "higher yields", "real yields", "rate hike", "rate cut", "fomc"),
        "primary_assets": {"TLT": "bearish", "IEF": "bearish", "QQQ": "bearish", "VOO": "mixed", "DXY": "bullish"},
        "secondary_assets": {"VIX": "mixed"},
        "impact_strength": "high",
        "transmission_path": "利率变化通过折现率、久期压力和美元流动性影响成长股、债券和大盘风险偏好。",
        "watch_items": ["10Y yield", "2Y yield", "real yields", "DXY", "VIX", "QQQ/SPY relative performance"],
    },
    {
        "risk_factor": "inflation",
        "keywords": ("inflation", "cpi", "pce", "price pressures", "disinflation"),
        "primary_assets": {"TLT": "bearish", "QQQ": "mixed", "VOO": "mixed", "GLD": "mixed"},
        "secondary_assets": {"DXY": "mixed", "VIX": "mixed"},
        "impact_strength": "medium",
        "transmission_path": "通胀数据会通过降息预期、实际利率和风险偏好影响债券、成长股和黄金。",
        "watch_items": ["CPI/PCE details", "10Y yield", "real yields", "DXY", "VIX"],
    },
    {
        "risk_factor": "semiconductors",
        "keywords": ("ai chips", "semiconductor", "semiconductors", "chip demand", "data center", "nvidia", "marvell", "advanced chips"),
        "primary_assets": {"NVDA": "mixed", "MRVL": "mixed", "AMD": "mixed", "AVGO": "mixed", "SMH": "mixed", "SOXX": "mixed"},
        "secondary_assets": {"QQQ": "mixed", "MSFT": "mixed"},
        "impact_strength": "medium",
        "transmission_path": "AI 与半导体事件通过芯片需求、数据中心资本开支和估值预期影响半导体链条与纳指资产。",
        "watch_items": ["SMH", "SOXX", "NVDA", "AMD", "AVGO", "AI capex commentary", "QQQ"],
    },
    {
        "risk_factor": "oil_supply",
        "keywords": ("oil", "crude", "brent", "wti", "opec", "hormuz", "shipping risk", "shipping disruption", "energy supply"),
        "primary_assets": {"WTI": "bullish", "Brent": "bullish", "USO": "bullish", "XLE": "bullish"},
        "secondary_assets": {"VOO": "mixed", "QQQ": "bearish", "GLD": "mixed"},
        "impact_strength": "medium",
        "transmission_path": "原油与能源供应事件主要通过油价、能源股现金流和通胀预期影响能源资产，并间接影响大盘风险偏好。",
        "watch_items": ["WTI", "Brent", "USO", "XLE", "inflation breakevens"],
    },
    {
        "risk_factor": "geopolitics_war",
        "keywords": ("war", "attack", "iran", "israel", "russia ukraine", "ukraine", "middle east", "shipping lanes"),
        "primary_assets": {"VIX": "bullish", "GLD": "bullish", "DXY": "mixed"},
        "secondary_assets": {"VOO": "mixed", "QQQ": "mixed"},
        "impact_strength": "medium",
        "transmission_path": "地缘冲突主要通过避险需求、波动率、美元和供应链风险影响黄金、VIX 和风险资产。",
        "watch_items": ["VIX", "gold", "DXY", "oil", "shipping rates"],
    },
    {
        "risk_factor": "trade_policy",
        "keywords": ("tariff", "tariffs", "sanction", "sanctions", "export control", "export controls"),
        "primary_assets": {"VOO": "mixed", "DXY": "mixed"},
        "secondary_assets": {"QQQ": "mixed", "VIX": "mixed"},
        "impact_strength": "medium",
        "transmission_path": "贸易与制裁政策需要先确认受影响商品或行业，再通过成本、需求和政策不确定性传导到资产价格。",
        "watch_items": ["policy details", "affected goods", "CPI pass-through", "affected companies", "VIX"],
    },
    {
        "risk_factor": "soft_commodities",
        "keywords": ("coffee", "cocoa", "sugar", "soft commodities"),
        "primary_assets": {"Coffee futures": "mixed", "CPI food component": "mixed"},
        "secondary_assets": {"Consumer Staples": "mixed"},
        "impact_strength": "low",
        "transmission_path": "软商品价格或关税主要通过食品价格和消费品成本传导，默认不直接影响大型科技股。",
        "watch_items": ["coffee futures", "affected goods", "CPI food component", "consumer staples margins"],
    },
    {
        "risk_factor": "musk_ecosystem",
        "keywords": ("spacex", "starlink"),
        "primary_assets": {"SpaceX / 私募估值": "mixed"},
        "secondary_assets": {"TSLA": "mixed"},
        "impact_strength": "low",
        "transmission_path": "SpaceX 属于 Elon Musk 关联生态和私募估值事件，对 TSLA 主要是间接情绪与管理层注意力传导，不等同于 TSLA 基本面事件。",
        "watch_items": ["TSLA relative to QQQ/SPY", "SpaceX valuation comps", "private market liquidity"],
    },
]


def map_assets(item: NewsItem, config: AppConfig) -> list[str]:
    return map_asset_impact(item, config).affected_assets


def map_asset_impact(item: NewsItem, config: AppConfig) -> AssetImpact:
    text = _event_text(item)
    company_assets = _mentioned_company_assets(item, text)
    rule = _select_rule(text)

    if _is_low_relevance_coal_event(text):
        return _empty_impact(item.title, "low_relevance")
    if _is_low_relevance_us_personnel_event(text):
        return _empty_impact(item.title, "low_relevance")

    if rule is None and company_assets:
        rule = _company_rule(company_assets)

    if rule is None:
        return _empty_impact(item.title, "low_relevance")

    risk_factor = str(rule["risk_factor"])
    preferred_companies = [] if risk_factor == "musk_ecosystem" else company_assets
    primary = _ordered_assets(_directions(rule, "primary_assets"), preferred_companies, risk_factor)
    secondary = _ordered_assets(_directions(rule, "secondary_assets"), [], risk_factor)

    if risk_factor == "trade_policy":
        primary, secondary = _narrow_trade_policy_assets(text, primary, secondary, company_assets)

    directions = {**{asset: _directions(rule, "primary_assets").get(asset, "mixed") for asset in primary}}
    directions.update({asset: _directions(rule, "secondary_assets").get(asset, "mixed") for asset in secondary})

    affected_assets = list(dict.fromkeys(primary + secondary))
    mapping_quality = "specific" if primary and risk_factor != "trade_policy" else "generic"
    if risk_factor in {"soft_commodities", "low_relevance"}:
        mapping_quality = "specific" if primary else "none"

    return AssetImpact(
        event=item.title,
        affected_assets=affected_assets,
        impact_direction=_aggregate_direction(directions),
        transmission_path=str(rule["transmission_path"]),
        per_asset_direction=directions,
        risk_factor=risk_factor,
        primary_assets=primary,
        secondary_assets=secondary,
        impact_strength=str(rule["impact_strength"]),
        watch_items=list(rule["watch_items"]),  # type: ignore[arg-type]
        mapping_quality=mapping_quality,
    )


def _event_text(item: NewsItem) -> str:
    return f"{item.title} {item.summary} {item.raw_content} {' '.join(item.symbols)}".lower()


def _select_rule(text: str) -> dict[str, object] | None:
    if "spacex" in text or "starlink" in text:
        return _rule("musk_ecosystem")
    if "coffee" in text and ("tariff" in text or "price" in text or "prices" in text):
        return _rule("soft_commodities")
    if ("crude" in text or _contains_token(text, "oil") or "wti" in text or "brent" in text or "hormuz" in text) and (
        "russia" in text or "sanction" in text or "export" in text or "opec" in text or "middle east" in text or "hormuz" in text
    ):
        return _rule("oil_supply")
    for rule in RISK_RULES:
        keywords = tuple(str(keyword).lower() for keyword in rule["keywords"])  # type: ignore[index]
        if any(_keyword_matches(text, keyword) for keyword in keywords):
            return rule
    return None


def _rule(risk_factor: str) -> dict[str, object]:
    for rule in RISK_RULES:
        if rule["risk_factor"] == risk_factor:
            return rule
    raise KeyError(risk_factor)


def _company_rule(company_assets: list[str]) -> dict[str, object]:
    semiconductor_names = {"NVDA", "MRVL", "AMD", "AVGO"}
    if any(asset in semiconductor_names for asset in company_assets):
        return _rule("semiconductors")
    return {
        "risk_factor": "company_specific",
        "primary_assets": {asset: "mixed" for asset in company_assets},
        "secondary_assets": {"QQQ": "mixed", "VOO": "mixed"},
        "impact_strength": "medium",
        "transmission_path": "公司事件主要通过盈利预期、估值和行业情绪影响相关个股，并间接影响所在指数。",
        "watch_items": company_assets + ["earnings commentary", "relative performance"],
    }


def _mentioned_company_assets(item: NewsItem, text: str) -> list[str]:
    assets: list[str] = []
    for symbol in item.symbols:
        normalized = symbol.upper()
        if normalized:
            assets.append(normalized)
    for term, asset in COMPANY_ASSETS.items():
        if _contains_token(text, term):
            assets.append(asset)
    return list(dict.fromkeys(assets))


def _contains_token(text: str, token: str) -> bool:
    if token.isupper() or len(token) <= 5:
        return bool(re.search(rf"(?<![a-z0-9]){re.escape(token.lower())}(?![a-z0-9])", text))
    return token.lower() in text


def _keyword_matches(text: str, keyword: str) -> bool:
    if keyword == "attack" and "attack dog" in text:
        return False
    if len(keyword) <= 5 or keyword.isupper():
        return _contains_token(text, keyword)
    return keyword in text


def _directions(rule: dict[str, object], field_name: str) -> dict[str, str]:
    assets = rule.get(field_name, {})
    if not isinstance(assets, dict):
        return {}
    return {str(asset): str(direction) for asset, direction in assets.items()}


def _ordered_assets(asset_directions: dict[str, str], preferred: list[str], risk_factor: str) -> list[str]:
    assets = list(dict.fromkeys(preferred + list(asset_directions.keys())))
    if risk_factor == "semiconductors":
        keep = set(preferred) | {"NVDA", "MRVL", "AMD", "AVGO", "SMH", "SOXX"}
        assets = [asset for asset in assets if asset in keep]
    return assets


def _narrow_trade_policy_assets(
    text: str,
    primary: list[str],
    secondary: list[str],
    company_assets: list[str],
) -> tuple[list[str], list[str]]:
    if "coffee" in text:
        return ["Coffee futures", "CPI food component"], ["Consumer Staples"]
    if any(term in text for term in ("ai chip", "semiconductor", "advanced chip", "export control")):
        semis = [asset for asset in ["NVDA", "MRVL", "AMD", "AVGO", "SMH", "SOXX"] if asset in company_assets or asset in {"SMH", "SOXX"}]
        return semis or ["SMH", "SOXX"], ["QQQ", "VIX"]
    if company_assets:
        return company_assets, ["QQQ", "VOO", "VIX"]
    return primary, secondary


def _is_low_relevance_coal_event(text: str) -> bool:
    if "coal mine" not in text and "mine disaster" not in text:
        return False
    qualifiers = ("energy supply", "coal price spike", "power shortage", "industrial production", "policy response")
    return not any(term in text for term in qualifiers)


def _is_low_relevance_us_personnel_event(text: str) -> bool:
    personnel_terms = ("spy chief", "appointment", "appoint", "nomination", "personnel")
    domestic_terms = ("trump", "white house", "congress", "pulte")
    conflict_terms = ("iran", "israel", "russia", "ukraine", "middle east", "sanction", "tariff", "war")
    return (
        any(term in text for term in personnel_terms)
        and any(term in text for term in domestic_terms)
        and not any(term in text for term in conflict_terms)
    )


def _empty_impact(title: str, risk_factor: str) -> AssetImpact:
    return AssetImpact(
        event=title,
        affected_assets=[],
        impact_direction="unclear",
        transmission_path="未找到明确、可投资的资产传导路径，默认作为低相关背景信息处理。",
        risk_factor=risk_factor,
        mapping_quality="none",
        impact_strength="low",
    )


def _aggregate_direction(directions: dict[str, str]) -> str:
    values = set(directions.values())
    if not values:
        return "unclear"
    if "bearish" in values and "bullish" in values:
        return "mixed"
    if "bearish" in values and "bullish" not in values:
        return "bearish"
    if "bullish" in values and "bearish" not in values:
        return "bullish"
    if values == {"mixed"}:
        return "mixed"
    return "mixed"
