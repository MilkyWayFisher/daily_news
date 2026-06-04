from __future__ import annotations

from datetime import datetime, timezone

from briefing.config import AppConfig
from briefing.models import AssetImpact, NewsItem, ScoredNews


HIGH_IMPACT_TERMS = (
    "federal reserve",
    "cpi",
    "pce",
    "tariff",
    "sanction",
    "export control",
    "war",
    "attack",
    "earnings",
    "guidance",
    "oil",
    "crude",
    "treasury yield",
    "rate cut",
    "rate hike",
    "middle east",
    "semiconductor",
    "ai",
)

BEARISH_TERMS = (
    "higher yields",
    "rate hike",
    "inflation rises",
    "tariff",
    "sanction",
    "export control",
    "misses estimates",
    "cuts guidance",
    "war",
    "attack",
    "supply disruption",
    "valuation pressure",
)

BULLISH_TERMS = (
    "rate cut",
    "beats estimates",
    "raises guidance",
    "cooling inflation",
    "lower yields",
    "stimulus",
    "supply increase",
)

HIGH_QUALITY_SOURCES = (
    "reuters",
    "associated press",
    "ap",
    "bloomberg",
    "wall street journal",
    "financial times",
    "cnbc",
    "federal reserve",
    "treasury",
    "bls",
    "bea",
    "fred",
)

SYSTEMIC_RISK_FACTORS = {"rates", "inflation", "oil_supply", "geopolitics_war", "trade_policy"}
DIRECT_RISK_FACTORS = {"semiconductors", "company_specific", "earnings"}


def score_item(
    item: NewsItem,
    category: str,
    related_assets: list[str],
    config: AppConfig,
    asset_impact: AssetImpact | None = None,
) -> ScoredNews:
    text = f"{item.title} {item.summary} {item.raw_content}".lower()
    impact = asset_impact or AssetImpact(
        event=item.title,
        affected_assets=related_assets,
        impact_direction=_impact_direction(text, category),
        transmission_path="",
    )
    freshness_hours = freshness_age_hours(item)
    freshness = _freshness_score(freshness_hours)
    relevance = _relevance_score(text, category, impact, config)
    importance = _importance_score(text, category, impact.risk_factor)
    asset_impact_score = _asset_impact_score(impact)
    source_quality = _source_quality_score(item)
    specificity = _specificity_score(text, impact)
    data_quality = _data_quality_score(item, impact)
    direction = impact.impact_direction if impact.impact_direction else _impact_direction(text, category)
    horizon = _time_horizon(category, impact.risk_factor)
    cap = _score_cap(freshness_hours, relevance, impact)
    final_estimate = (
        freshness * 0.25
        + relevance * 0.25
        + importance * 0.20
        + asset_impact_score * 0.15
        + source_quality * 0.05
        + specificity * 0.05
        + data_quality * 0.05
    )
    assumption_changed = min(int(round(final_estimate * 100)), cap) >= 85 and horizon in {
        "medium-term",
        "long-term",
    }
    is_new = freshness_hours is None or freshness_hours <= 36
    likely_digested = (
        (freshness_hours is not None and freshness_hours > 36)
        or "priced in" in text
        or "already reflected" in text
    )

    return ScoredNews(
        item=item,
        category=category,
        related_assets=related_assets,
        impact_direction=direction,
        time_horizon=horizon,
        relevance_score=round(relevance, 3),
        importance_score=round(importance, 3),
        novelty_score=round(freshness, 3),
        market_impact_score=round(asset_impact_score, 3),
        confidence_score=round((source_quality + specificity + data_quality) / 3, 3),
        reasoning=_reasoning(category, direction, horizon, impact),
        watch_items=list(dict.fromkeys(impact.watch_items or _fallback_watch_items(impact.risk_factor))),
        investment_assumption_changed=assumption_changed,
        transmission_path=impact.transmission_path,
        affected_asset_directions=impact.per_asset_direction,
        is_new_information=is_new,
        likely_market_digested=likely_digested,
        risk_factor=impact.risk_factor,
        primary_assets=impact.primary_assets,
        secondary_assets=impact.secondary_assets,
        impact_strength=impact.impact_strength,
        freshness_score=round(freshness, 3),
        source_quality_score=round(source_quality, 3),
        specificity_score=round(specificity, 3),
        data_quality_score=round(data_quality, 3),
        freshness_hours=None if freshness_hours is None else round(freshness_hours, 2),
        score_cap=cap,
        mapping_quality=impact.mapping_quality,
    )


def freshness_age_hours(item: NewsItem) -> float | None:
    try:
        parsed = datetime.fromisoformat(item.published_at)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        age = (datetime.now(timezone.utc) - parsed.astimezone(timezone.utc)).total_seconds() / 3600
        return max(0.0, age)
    except (TypeError, ValueError):
        return None


def is_daily_eligible(item: NewsItem) -> bool:
    age = freshness_age_hours(item)
    if age is None:
        return True
    if age <= 36:
        return True
    if str(item.metadata.get("window_status") or "") in {"outside_window_retained", "major_update_retained"}:
        return True
    role = str(item.metadata.get("role") or item.metadata.get("coverage") or "").lower()
    return role in {"follow_up", "background", "weekly_review"}


def _freshness_score(age_hours: float | None) -> float:
    if age_hours is None:
        return 0.45
    if age_hours <= 24:
        return 1.0
    if age_hours <= 48:
        return 0.60
    if age_hours <= 96:
        return 0.35
    if age_hours <= 168:
        return 0.25
    return 0.05


def _relevance_score(text: str, category: str, impact: AssetImpact, config: AppConfig) -> float:
    if category == "low_relevance" or impact.risk_factor == "low_relevance":
        return 0.10
    watchlist_hits = sum(1 for ticker in config.watchlist.tickers if _contains_ticker(text, ticker))
    topic_hits = sum(1 for term in config.topics.all_terms if term.lower() in text)
    if watchlist_hits or impact.risk_factor in DIRECT_RISK_FACTORS:
        return min(1.0, 0.72 + watchlist_hits * 0.08 + min(topic_hits, 2) * 0.05)
    if impact.risk_factor in SYSTEMIC_RISK_FACTORS:
        return 0.78
    if impact.risk_factor == "soft_commodities":
        return 0.42
    if impact.primary_assets:
        return 0.62
    return min(0.50, 0.25 + min(topic_hits, 3) * 0.08)


def _importance_score(text: str, category: str, risk_factor: str) -> float:
    term_hits = sum(1 for term in HIGH_IMPACT_TERMS if term in text)
    base = {
        "rates": 0.78,
        "inflation": 0.75,
        "oil_supply": 0.72,
        "geopolitics_war": 0.70,
        "trade_policy": 0.62,
        "semiconductors": 0.68,
        "company_specific": 0.55,
        "soft_commodities": 0.35,
        "low_relevance": 0.10,
    }.get(risk_factor, 0.42)
    if category == "earnings":
        base = max(base, 0.70)
    return min(1.0, base + min(term_hits, 4) * 0.04)


def _asset_impact_score(impact: AssetImpact) -> float:
    if impact.mapping_quality == "none" or not impact.primary_assets:
        return 0.10
    if impact.mapping_quality == "generic":
        return 0.35
    strength_boost = {"high": 0.22, "medium": 0.14, "low": 0.05}.get(impact.impact_strength, 0.05)
    asset_boost = min(len(impact.primary_assets), 5) * 0.06
    return min(1.0, 0.42 + strength_boost + asset_boost)


def _source_quality_score(item: NewsItem) -> float:
    source = item.source.lower()
    if any(name in source for name in HIGH_QUALITY_SOURCES):
        return 0.95
    if item.source:
        return 0.65
    return 0.35


def _specificity_score(text: str, impact: AssetImpact) -> float:
    if impact.mapping_quality == "none":
        return 0.15
    if impact.mapping_quality == "generic":
        return 0.42
    has_named_asset = bool(impact.primary_assets)
    has_specific_term = any(
        term in text
        for term in ("yield", "cpi", "pce", "oil", "crude", "nvidia", "marvell", "earnings", "guidance")
    )
    return 0.85 if has_named_asset and has_specific_term else 0.65


def _data_quality_score(item: NewsItem, impact: AssetImpact) -> float:
    score = 0.30
    if item.url:
        score += 0.20
    if item.published_at:
        score += 0.20
    if item.summary or item.raw_content:
        score += 0.20
    if impact.transmission_path and impact.mapping_quality != "none":
        score += 0.10
    return min(1.0, score)


def _score_cap(age_hours: float | None, relevance: float, impact: AssetImpact) -> int:
    cap = 100
    if age_hours is not None:
        if age_hours > 168:
            cap = min(cap, 20)
        elif age_hours > 72:
            cap = min(cap, 40)
        elif age_hours > 36:
            cap = min(cap, 60)
    if relevance < 0.40:
        cap = min(cap, 50)
    if impact.mapping_quality == "generic":
        cap = min(cap, 60)
    if impact.mapping_quality == "none" or not impact.transmission_path:
        cap = min(cap, 65)
    return cap


def _impact_direction(text: str, category: str) -> str:
    bearish = sum(1 for term in BEARISH_TERMS if term in text)
    bullish = sum(1 for term in BULLISH_TERMS if term in text)
    if bearish and bullish:
        return "mixed"
    if bearish:
        return "bearish"
    if bullish:
        return "bullish"
    if category in {"geopolitics", "policy", "commodity"}:
        return "mixed"
    return "unclear"


def _time_horizon(category: str, risk_factor: str) -> str:
    if category == "market":
        return "short-term"
    if risk_factor in {"rates", "inflation", "oil_supply", "geopolitics_war", "trade_policy"}:
        return "medium-term"
    if category in {"earnings", "company", "sector"}:
        return "medium-term"
    return "short-term"


def _reasoning(category: str, direction: str, horizon: str, impact: AssetImpact) -> str:
    assets = "、".join(impact.primary_assets) if impact.primary_assets else "未明确映射资产"
    direction_zh = {
        "bullish": "偏利好",
        "bearish": "偏利空",
        "mixed": "影响复杂",
        "unclear": "方向暂不明确",
    }.get(direction, "方向暂不明确")
    horizon_zh = {
        "intraday": "盘中",
        "short-term": "短期",
        "medium-term": "中期",
        "long-term": "长期",
    }.get(horizon, "短期")
    return (
        f"该事件属于{category}，risk_factor={impact.risk_factor}，"
        f"主要通过{impact.transmission_path or '尚不明确的路径'}影响{assets}，"
        f"{horizon_zh}方向{direction_zh}。"
    )


def _fallback_watch_items(risk_factor: str) -> list[str]:
    return {
        "rates": ["10Y yield", "2Y yield", "DXY", "VIX"],
        "inflation": ["CPI/PCE details", "10Y yield", "real yields"],
        "oil_supply": ["WTI", "Brent", "USO", "XLE"],
        "semiconductors": ["SMH", "SOXX", "NVDA", "AI capex commentary"],
        "trade_policy": ["policy details", "affected goods", "CPI pass-through"],
        "geopolitics_war": ["VIX", "gold", "oil", "DXY"],
    }.get(risk_factor, ["news confirmation", "related asset price action"])


def _contains_ticker(text: str, ticker: str) -> bool:
    return ticker.lower() in text
