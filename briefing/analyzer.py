from __future__ import annotations

import json
import os
from typing import Any

from briefing.config import AppConfig
from briefing.env import first_env
from briefing.guardrails import sanitize_text
from briefing.http import HttpError, post_json
from briefing.models import Briefing, EventCluster, MacroIndicator, MarketPoint, ScoredNews, utc_now_iso


DISCLAIMER = "本简报仅用于信息整理和投资研究辅助，不构成个性化投资建议。"


def build_briefing(
    date: str,
    scored_news: list[ScoredNews],
    market_points: list[MarketPoint],
    macro_indicators: list[MacroIndicator],
    config: AppConfig,
    raw_counts: dict[str, int],
    warnings: list[str] | None = None,
    market_confidence: str = "medium",
    event_clusters: list[EventCluster] | None = None,
    debug_notes: list[str] | None = None,
    generated_at: str | None = None,
    data_window_start: str = "",
    data_window_end: str = "",
) -> Briefing:
    top_news = sorted(scored_news, key=lambda item: item.final_score, reverse=True)[
        : config.rules.max_news_items
    ]
    top_news = _maybe_llm_refine(top_news, config)
    return Briefing(
        date=date,
        generated_at=generated_at or utc_now_iso(),
        core_view=_core_view(top_news, market_points, macro_indicators),
        top_news=top_news,
        geopolitical_risks=_geopolitical_risks(top_news),
        market_environment=_market_environment(top_news, market_points, macro_indicators),
        watchlist=config.watchlist.tickers,
        assumption_change=_assumption_change(top_news, event_clusters or []),
        disclaimer=DISCLAIMER,
        raw_counts=raw_counts,
        market_points=market_points,
        macro_indicators=macro_indicators,
        warnings=warnings or [],
        market_confidence=market_confidence,
        event_clusters=event_clusters or [],
        debug_notes=debug_notes or [],
        data_window_start=data_window_start,
        data_window_end=data_window_end,
    )


def _core_view(
    top_news: list[ScoredNews],
    market_points: list[MarketPoint],
    macro_indicators: list[MacroIndicator],
) -> str:
    if not top_news:
        return "今日数据源暂未返回足够高相关性的事件，适合以宏观数据和市场价格变化作为主要观察对象。"

    risk = _risk_level(top_news)
    drivers = "、".join(list(dict.fromkeys(item.category for item in top_news[:3])))
    variable = _important_variable(top_news, market_points, macro_indicators)
    voo_view = _asset_view("VOO", top_news)
    qqq_view = _asset_view("QQQ", top_news)
    tech_view = _group_view(["QQQ", "NVDA", "MSFT", "AAPL", "SMH"], top_news)
    energy_view = _group_view(["XLE", "USO"], top_news)
    bond_view = _group_view(["TLT", "10Y Treasury Yield", "2Y Treasury Yield"], top_news)
    return sanitize_text(
        f"市场风险等级：{risk}。市场数据置信度：{_confidence_zh(_market_confidence(market_points, macro_indicators))}。今日主要驱动因素：{drivers}。"
        f"今日最重要变量：{variable}。"
        f"对 VOO：{voo_view}。对 QQQ：{qqq_view}。"
        f"对科技股：{tech_view}。对能源：{energy_view}。对债券：{bond_view}。"
        "系统判断：暂不改变长期投资假设，继续等待价格确认和后续数据。"
    )


def _geopolitical_risks(top_news: list[ScoredNews]) -> list[str]:
    risks = []
    for item in top_news:
        if item.category == "geopolitics" or item.risk_factor == "geopolitics_war":
            assets = "、".join(item.primary_assets or item.related_assets) if item.related_assets else "能源、黄金和风险资产"
            risks.append(
                f"{item.item.title}：可能通过{item.transmission_path or '风险偏好与能源价格'}影响{assets}。"
            )
    return risks[:4]


def _market_environment(
    top_news: list[ScoredNews],
    market_points: list[MarketPoint],
    macro_indicators: list[MacroIndicator],
) -> list[str]:
    environment: list[str] = []
    confidence = _market_confidence(market_points, macro_indicators)
    if confidence == "low":
        environment.append("市场数据覆盖不足，今日市场判断置信度降低。")
    if any(item.category in {"macro", "rates"} for item in top_news):
        environment.append("宏观焦点集中在利率路径、通胀数据和美债收益率变化。")
    if any(item.category in {"sector", "company", "earnings"} for item in top_news):
        environment.append("科技和 AI 相关资产需要观察估值、盈利增长和资本开支是否匹配。")

    for point in market_points[:10]:
        if not point.available:
            environment.append(f"{point.symbol}：数据暂不可用。")
            continue
        value = "暂无价格" if point.last_price is None else f"{point.last_price:.2f}"
        change = (
            "日变动暂不可用"
            if point.daily_change_pct is None
            else f"日变动 {point.daily_change_pct:.2f}%"
        )
        environment.append(f"{point.symbol}：{value}，{change}。")

    for indicator in macro_indicators[:6]:
        if not indicator.available:
            environment.append(f"{indicator.indicator}：数据暂不可用。")
        else:
            environment.append(
                f"{indicator.indicator}：{indicator.latest_value}，数据期 {indicator.release_date}，{indicator.interpretation}"
            )
    return environment[:14]


def _assumption_change(top_news: list[ScoredNews], clusters: list[EventCluster]) -> str:
    changed_clusters = [
        cluster
        for cluster in clusters
        if cluster.final_score >= 85
        and cluster.transmission_path
        and cluster.price_confirmation.status == "short_price_sync"
        and any(item.time_horizon in {"medium-term", "long-term"} for item in cluster.items)
        and _touches_core_assets_or_macro(cluster)
    ]
    if changed_clusters:
        titles = "；".join(cluster.title for cluster in changed_clusters[:2])
        return f"暂不确定。以下事件达到长期假设观察阈值，需要后续数据确认：{titles}"
    return "暂不改变长期投资假设。当前更适合观察价格确认和后续数据。"


def _touches_core_assets_or_macro(cluster: EventCluster) -> bool:
    core_assets = {"VOO", "SPY", "QQQ", "TLT", "GLD", "XLE", "USO", "VIX", "DXY", "WTI"}
    core_risk_factors = {"rates", "inflation", "oil_supply", "geopolitics_war", "trade_policy"}
    return bool(set(cluster.primary_assets + cluster.secondary_assets) & core_assets) or cluster.risk_factor in core_risk_factors


def _risk_level(top_news: list[ScoredNews]) -> str:
    bearish_or_mixed = sum(1 for item in top_news if item.impact_direction in {"bearish", "mixed"})
    high_score = sum(1 for item in top_news if item.final_score >= 75)
    if bearish_or_mixed >= 4 or high_score >= 3:
        return "中高"
    if bearish_or_mixed >= 2 or high_score >= 1:
        return "中等"
    return "低到中等"


def _important_variable(
    top_news: list[ScoredNews],
    market_points: list[MarketPoint],
    macro_indicators: list[MacroIndicator],
) -> str:
    risk_factors = {item.risk_factor for item in top_news[:5]}
    text = " ".join(item.item.title.lower() for item in top_news[:5])
    if "rates" in risk_factors or "yield" in text or any("Treasury" in point.name for point in market_points):
        return "美债收益率与降息预期"
    if "oil_supply" in risk_factors or "oil" in text or "middle east" in text:
        return "油价与地缘政治风险"
    if "semiconductors" in risk_factors or "ai" in text or "semiconductor" in text or "nvidia" in text:
        return "AI 与半导体估值预期"
    if any(indicator.available for indicator in macro_indicators):
        return "本周宏观数据确认度"
    return "风险偏好是否延续"


def _asset_view(asset: str, top_news: list[ScoredNews]) -> str:
    directions = [
        item.affected_asset_directions.get(asset)
        for item in top_news
        if item.affected_asset_directions.get(asset)
    ]
    return _direction_summary(directions)


def _group_view(assets: list[str], top_news: list[ScoredNews]) -> str:
    directions: list[str] = []
    for item in top_news:
        for asset in assets:
            direction = item.affected_asset_directions.get(asset)
            if direction:
                directions.append(direction)
    return _direction_summary(directions)


def _direction_summary(directions: list[str | None]) -> str:
    clean = [direction for direction in directions if direction]
    if not clean:
        return "暂无明确方向，重点观察价格确认"
    if clean.count("bearish") > clean.count("bullish"):
        return "短期偏谨慎，需要观察压力是否延续"
    if clean.count("bullish") > clean.count("bearish"):
        return "短期偏正面，但仍需观察是否被价格消化"
    return "影响复杂，适合观察而非基于单一事件行动"


def _maybe_llm_refine(top_news: list[ScoredNews], config: AppConfig) -> list[ScoredNews]:
    api_key = first_env("OPENAI_API_KEY", "LLM_API_KEY")
    if not api_key or not top_news:
        return top_news

    payload = _openai_payload(top_news, config)
    try:
        response = post_json(
            "https://api.openai.com/v1/responses",
            payload,
            timeout=45,
            headers={"Authorization": f"Bearer {api_key}"},
        )
    except HttpError:
        return top_news

    text = _extract_response_text(response)
    if not text:
        return top_news
    try:
        refinements = json.loads(text)
    except json.JSONDecodeError:
        return top_news
    if not isinstance(refinements, list):
        return top_news

    by_url = {
        item.get("url"): item
        for item in refinements
        if isinstance(item, dict) and isinstance(item.get("url"), str)
    }
    for scored in top_news:
        refinement = by_url.get(scored.item.url)
        if not refinement:
            continue
        reasoning = refinement.get("reasoning")
        watch_items = refinement.get("watch_items")
        transmission_path = refinement.get("transmission_path")
        if isinstance(reasoning, str) and reasoning:
            scored.reasoning = sanitize_text(reasoning)
        if isinstance(transmission_path, str) and transmission_path:
            scored.transmission_path = sanitize_text(transmission_path)
        if isinstance(watch_items, list):
            scored.watch_items = [str(item) for item in watch_items if item]
    return top_news


def _openai_payload(top_news: list[ScoredNews], config: AppConfig) -> dict[str, Any]:
    model = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")
    items = [
        {
            "title": scored.item.title,
            "summary": scored.item.summary,
            "source": scored.item.source,
            "url": scored.item.url,
            "category": scored.category,
            "related_assets": scored.related_assets,
            "impact_direction": scored.impact_direction,
            "time_horizon": scored.time_horizon,
            "transmission_path": scored.transmission_path,
            "risk_factor": scored.risk_factor,
            "primary_assets": scored.primary_assets,
            "secondary_assets": scored.secondary_assets,
        }
        for scored in top_news
    ]
    prompt = (
        "你是投资研究助理。请基于新闻事实，为每条新闻补充中文 reasoning、transmission_path 和 watch_items。"
        "禁止输出直接买卖指令、保证收益或过度确定性语言。只输出 JSON 数组。"
        f"用户关注资产：{config.watchlist.tickers}。新闻：{json.dumps(items, ensure_ascii=False)}"
    )
    return {
        "model": model,
        "input": prompt,
        "text": {"format": {"type": "text"}},
    }


def _extract_response_text(response: dict[str, Any]) -> str:
    chunks: list[str] = []
    for output in response.get("output", []) or []:
        for content in output.get("content", []) or []:
            text = content.get("text")
            if isinstance(text, str):
                chunks.append(text)
    return "".join(chunks).strip()


def _market_confidence(
    market_points: list[MarketPoint],
    macro_indicators: list[MacroIndicator],
) -> str:
    total = len(market_points) + len(macro_indicators)
    if total == 0:
        return "low"
    available = sum(1 for point in market_points if point.available) + sum(
        1 for indicator in macro_indicators if indicator.available
    )
    coverage = available / total
    if coverage >= 0.80:
        return "high"
    if coverage >= 0.60:
        return "medium"
    return "low"


def _confidence_zh(confidence: str) -> str:
    return {"high": "高", "medium": "中", "low": "低"}.get(confidence, "中")
