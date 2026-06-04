from __future__ import annotations

from briefing.compat import dataclass_compat
from datetime import date, datetime, timedelta, timezone

from briefing.analyzer import build_briefing
from briefing.asset_mapper import map_asset_impact
from briefing.classifier import classify
from briefing.collectors import (
    AlphaVantageMarketCollector,
    AlphaVantageNewsCollector,
    FredMacroCollector,
    GdeltCollector,
    NewsApiCollector,
    RssCollector,
)
from briefing.config import AppConfig
from briefing.collectors.macro import unavailable_macro
from briefing.dedupe import dedupe_items
from briefing.env import first_env
from briefing.event_clusterer import cluster_events
from briefing.models import Briefing, MacroIndicator, MarketPoint, NewsItem, ScoredNews, utc_now_iso
from briefing.normalizer import normalize_items
from briefing.renderer import render_markdown
from briefing.sample_data import sample_news
from briefing.scoring import is_daily_eligible, score_item
from briefing.storage import FileStorage
from briefing.output_checker import apply_output_guardrails


@dataclass_compat(slots=True)
class PipelineResult:
    briefing: Briefing
    markdown: str
    raw_items: list[NewsItem]
    scored_items: list[ScoredNews]
    saved_dir: str | None
    delivered: bool


def run_pipeline(
    config: AppConfig,
    *,
    run_date: str | None = None,
    demo: bool = False,
    dry_run: bool = False,
    save: bool = True,
) -> PipelineResult:
    target_date = run_date or date.today().isoformat()
    window_start, window_end = _briefing_window(config)
    warnings: list[str] = []
    debug_notes: list[str] = []
    raw_items = sample_news() if demo else _collect_news(config)
    if not raw_items:
        warnings.append("新闻数据源未返回内容，已继续生成简报。")

    normalized = normalize_items(raw_items)
    selected_items, news_stats = (
        (normalized, _demo_news_stats(normalized))
        if demo
        else _select_news_for_scoring(normalized, config, window_start, window_end)
    )
    deduped = dedupe_items(selected_items)
    scored = _score_news(deduped, config)
    market_points = _collect_market(config, warnings)
    macro_indicators = _collect_macro(config, warnings)
    market_confidence = _market_confidence(market_points, macro_indicators)
    if market_confidence == "low":
        warnings.append("市场数据覆盖不足，今日市场判断置信度降低。")
    scored, guardrail_warnings = apply_output_guardrails(scored, market_confidence=market_confidence)
    debug_notes.extend(guardrail_warnings)
    filtered = [item for item in scored if _include_scored_item(item, config)]
    event_clusters, cluster_stats = cluster_events(filtered, market_points, macro_indicators)
    coverage_pct = int(round(_market_coverage(market_points, macro_indicators) * 100))
    briefing = build_briefing(
        target_date,
        filtered,
        market_points,
        macro_indicators,
        config,
        raw_counts={
            "raw": len(raw_items),
            "normalized": len(normalized),
            "windowed": news_stats["in_window"],
            "in_window": news_stats["in_window"],
            "outside_window_retained": news_stats["outside_retained"],
            "filtered_out": news_stats["filtered_out"],
            "filtered_outside_window": news_stats["outside_filtered"],
            "selected_for_scoring": len(selected_items),
            "deduped": len(deduped),
            "scored": len(scored),
            "filtered": len(filtered),
            "body_news": len(filtered),
            "clusters": cluster_stats["cluster_count"],
            "market_coverage_pct": coverage_pct,
        },
        warnings=warnings,
        market_confidence=market_confidence,
        event_clusters=event_clusters,
        debug_notes=debug_notes,
        generated_at=window_end,
        data_window_start=window_start,
        data_window_end=window_end,
    )
    markdown = render_markdown(briefing)

    saved_dir = None
    if save and config.rules.save_history:
        saved_dir = str(FileStorage().save(target_date, raw_items, filtered, briefing, markdown))

    delivered = False
    if not dry_run:
        delivered = _deliver(markdown, target_date, config)

    return PipelineResult(
        briefing=briefing,
        markdown=markdown,
        raw_items=raw_items,
        scored_items=filtered,
        saved_dir=saved_dir,
        delivered=delivered,
    )


def _deliver(markdown: str, target_date: str, config: AppConfig) -> bool:
    channel = config.delivery.channel.lower()
    if channel == "telegram":
        from briefing.delivery import TelegramDelivery

        return TelegramDelivery().send_markdown(markdown)
    if channel == "email":
        from briefing.delivery import EmailDelivery

        subject = f"{config.delivery.email.subject_prefix}：{target_date}"
        return EmailDelivery().send_markdown(markdown, subject)
    return False


def _collect_news(config: AppConfig) -> list[NewsItem]:
    collectors = []
    if config.sources.newsapi:
        collectors.append(NewsApiCollector())
    if config.sources.gdelt:
        collectors.append(GdeltCollector())
    if config.sources.alphavantage_news:
        collectors.append(AlphaVantageNewsCollector())
    if config.sources.rss:
        collectors.append(RssCollector())

    items: list[NewsItem] = []
    for collector in collectors:
        items.extend(collector.collect(config))
    return items


def _collect_market(config: AppConfig, warnings: list[str]) -> list[MarketPoint]:
    if not config.sources.alphavantage_market:
        warnings.append("市场数据源已在配置中关闭。")
        return _unavailable_market(config.market.symbols, "市场数据源已关闭")

    symbols = list(dict.fromkeys(config.market.symbols + config.watchlist.tickers))
    if not first_env("ALPHAVANTAGE_API_KEY", "ALPHAVANTAGE_KEY"):
        warnings.append("缺少 ALPHAVANTAGE_API_KEY / ALPHAVANTAGE_KEY，市场数据标记为暂不可用。")
        return _unavailable_market(symbols, "缺少 Alpha Vantage key")

    points = AlphaVantageMarketCollector().collect(symbols)
    returned = {point.symbol for point in points}
    missing = [symbol for symbol in symbols if symbol not in returned]
    if missing:
        warnings.append("部分市场数据暂不可用：" + ", ".join(missing[:8]))
        points.extend(_unavailable_market(missing, "API 未返回该指标"))
    return points


def _collect_macro(config: AppConfig, warnings: list[str]) -> list[MacroIndicator]:
    indicators = config.macro.indicators
    if not config.sources.fred_macro:
        warnings.append("宏观数据源已在配置中关闭。")
        return unavailable_macro(indicators, "宏观数据源已关闭")
    if not first_env("FRED_API_KEY"):
        warnings.append("缺少 FRED_API_KEY，宏观数据标记为暂不可用。")
        return unavailable_macro(indicators[:8], "缺少 FRED_API_KEY")
    collected = FredMacroCollector().collect(indicators, lookback_months=config.macro.macro_lookback_months)
    returned = {indicator.indicator for indicator in collected}
    missing = [indicator for indicator in indicators if indicator not in returned]
    if missing:
        warnings.append("部分宏观数据暂不可用：" + ", ".join(missing[:8]))
        collected.extend(unavailable_macro(missing[:8], "FRED 未返回该指标"))
    return collected


def _score_news(items: list[NewsItem], config: AppConfig) -> list[ScoredNews]:
    scored: list[ScoredNews] = []
    for item in items:
        category = classify(item)
        asset_impact = map_asset_impact(item, config)
        scored.append(score_item(item, category, asset_impact.affected_assets, config, asset_impact))
    return sorted(scored, key=lambda item: item.final_score, reverse=True)


def _include_scored_item(item: ScoredNews, config: AppConfig) -> bool:
    threshold = config.rules.min_score * 100 if config.rules.min_score <= 1 else config.rules.min_score
    if not is_daily_eligible(item.item):
        return False
    if item.category == "low_relevance":
        return False
    return item.final_score >= threshold


def _market_confidence(
    market_points: list[MarketPoint],
    macro_indicators: list[MacroIndicator],
) -> str:
    coverage = _market_coverage(market_points, macro_indicators)
    core_coverage = _core_market_coverage(market_points)
    if coverage <= 0:
        return "low"
    if coverage >= 0.80:
        return "high"
    if core_coverage >= 0.90 or coverage >= 0.50:
        return "medium"
    return "low"


def _market_coverage(
    market_points: list[MarketPoint],
    macro_indicators: list[MacroIndicator],
) -> float:
    total = len(market_points) + len(macro_indicators)
    if total == 0:
        return 0.0
    available = sum(1 for point in market_points if point.available) + sum(
        1 for indicator in macro_indicators if indicator.available
    )
    return available / total


def _core_market_coverage(market_points: list[MarketPoint]) -> float:
    core_assets = {"SPY", "QQQ", "NVDA", "TLT", "GLD", "XLE", "VIX", "DXY", "WTI"}
    relevant = [point for point in market_points if point.symbol.upper() in core_assets]
    if not relevant:
        return 0.0
    available = sum(1 for point in relevant if point.available)
    return available / len(relevant)


def _unavailable_market(symbols: list[str], reason: str) -> list[MarketPoint]:
    return [
        MarketPoint(
            symbol=symbol,
            name=symbol,
            source="unavailable",
            updated_at=utc_now_iso(),
            available=False,
            note=reason,
            raw={"reason": reason},
        )
        for symbol in symbols
    ]


def _briefing_window(config: AppConfig) -> tuple[str, str]:
    end = datetime.now(timezone.utc)
    hours = max(1, int(config.sources.news_lookback_hours or 24))
    start = end - timedelta(hours=hours)
    return start.isoformat(timespec="seconds"), end.isoformat(timespec="seconds")


def _select_news_for_scoring(
    items: list[NewsItem],
    config: AppConfig,
    start_iso: str,
    end_iso: str,
) -> tuple[list[NewsItem], dict[str, int]]:
    start = _parse_datetime(start_iso)
    end = _parse_datetime(end_iso)
    stats = {"in_window": 0, "outside_retained": 0, "outside_filtered": 0, "filtered_out": 0}
    if start is None or end is None or start >= end:
        stats["in_window"] = len(items)
        return items, stats
    selected: list[NewsItem] = []
    for item in items:
        published = _parse_datetime(item.published_at)
        if published is None or start <= published <= end:
            item.metadata["window_status"] = "in_window"
            item.metadata["recency_score"] = 1.0
            selected.append(item)
            stats["in_window"] += 1
            continue

        age_hours = (end - published).total_seconds() / 3600 if published else None
        if age_hours is not None and 0 <= age_hours <= 48 and _is_high_relevance_candidate(item, config):
            item.metadata["window_status"] = "outside_window_retained"
            item.metadata["recency_score"] = 0.6
            selected.append(item)
            stats["outside_retained"] += 1
            continue
        if age_hours is not None and 48 < age_hours <= 96 and _is_major_update(item, config):
            item.metadata["window_status"] = "major_update_retained"
            item.metadata["recency_score"] = 0.35
            selected.append(item)
            stats["outside_retained"] += 1
            continue
        stats["outside_filtered"] += 1
        stats["filtered_out"] += 1
    return selected, stats


def _demo_news_stats(items: list[NewsItem]) -> dict[str, int]:
    return {
        "in_window": len(items),
        "outside_retained": 0,
        "outside_filtered": 0,
        "filtered_out": 0,
    }


def _is_high_relevance_candidate(item: NewsItem, config: AppConfig) -> bool:
    category = classify(item)
    if category == "low_relevance":
        return False
    impact = map_asset_impact(item, config)
    assets = set(impact.primary_assets + impact.secondary_assets)
    watchlist = set(config.watchlist.tickers)
    systemic = {"rates", "inflation", "oil_supply", "geopolitics_war", "trade_policy", "semiconductors"}
    return bool(assets & watchlist) or impact.risk_factor in systemic


def _is_major_update(item: NewsItem, config: AppConfig) -> bool:
    text = f"{item.title} {item.summary} {item.raw_content}".lower()
    major_terms = (
        "breaking",
        "federal reserve decision",
        "fomc decision",
        "cpi report",
        "pce report",
        "earnings guidance",
        "cuts guidance",
        "raises guidance",
        "war",
        "attack",
        "sanction",
        "tariff",
        "default",
        "bank failure",
        "opec",
    )
    return any(term in text for term in major_terms) and _is_high_relevance_candidate(item, config)


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
    return parsed.astimezone(timezone.utc)
