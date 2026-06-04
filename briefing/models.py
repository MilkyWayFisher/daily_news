from __future__ import annotations

from dataclasses import asdict, field
from datetime import datetime, timezone
from typing import Any

from briefing.compat import dataclass_compat


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass_compat(slots=True)
class NewsItem:
    title: str
    source: str
    url: str
    published_at: str
    summary: str = ""
    raw_content: str = ""
    language: str = ""
    source_type: str = "news"
    symbols: list[str] = field(default_factory=list)
    entities: list[str] = field(default_factory=list)
    topics: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["content"] = self.raw_content
        return data


@dataclass_compat(slots=True)
class MarketPoint:
    symbol: str
    value: float | None = None
    change_percent: float | None = None
    timestamp: str = ""
    source: str = ""
    raw: dict[str, Any] = field(default_factory=dict)
    name: str = ""
    last_price: float | None = None
    daily_change_pct: float | None = None
    weekly_change_pct: float | None = None
    monthly_change_pct: float | None = None
    updated_at: str = ""
    available: bool = True
    note: str = ""

    def __post_init__(self) -> None:
        if self.last_price is None:
            self.last_price = self.value
        if self.daily_change_pct is None:
            self.daily_change_pct = self.change_percent
        if not self.updated_at:
            self.updated_at = self.timestamp or utc_now_iso()
        if not self.timestamp:
            self.timestamp = self.updated_at
        if not self.name:
            self.name = self.symbol

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "name": self.name,
            "last_price": self.last_price,
            "daily_change_pct": self.daily_change_pct,
            "weekly_change_pct": self.weekly_change_pct,
            "monthly_change_pct": self.monthly_change_pct,
            "source": self.source,
            "updated_at": self.updated_at,
            "available": self.available,
            "note": self.note,
            "raw": self.raw,
        }


@dataclass_compat(slots=True)
class MacroIndicator:
    indicator: str
    latest_value: float | None
    previous_value: float | None
    release_date: str
    source: str
    interpretation: str
    available: bool = True
    raw: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass_compat(slots=True)
class AssetImpact:
    event: str
    affected_assets: list[str]
    impact_direction: str
    transmission_path: str
    per_asset_direction: dict[str, str] = field(default_factory=dict)
    risk_factor: str = "low_relevance"
    primary_assets: list[str] = field(default_factory=list)
    secondary_assets: list[str] = field(default_factory=list)
    impact_strength: str = "low"
    watch_items: list[str] = field(default_factory=list)
    mapping_quality: str = "none"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass_compat(slots=True)
class ScoredNews:
    item: NewsItem
    category: str
    related_assets: list[str]
    impact_direction: str
    time_horizon: str
    relevance_score: float
    importance_score: float
    novelty_score: float
    market_impact_score: float
    confidence_score: float
    reasoning: str
    watch_items: list[str]
    investment_assumption_changed: bool = False
    transmission_path: str = ""
    affected_asset_directions: dict[str, str] = field(default_factory=dict)
    is_new_information: bool = True
    likely_market_digested: bool = False
    risk_factor: str = "low_relevance"
    primary_assets: list[str] = field(default_factory=list)
    secondary_assets: list[str] = field(default_factory=list)
    impact_strength: str = "low"
    freshness_score: float = 0.0
    source_quality_score: float = 0.0
    specificity_score: float = 0.0
    data_quality_score: float = 0.0
    freshness_hours: float | None = None
    score_cap: int = 100
    mapping_quality: str = "none"

    @property
    def total_score(self) -> float:
        score = (
            self.freshness_score * 0.25
            + self.relevance_score * 0.25
            + self.importance_score * 0.20
            + self.market_impact_score * 0.15
            + self.source_quality_score * 0.05
            + self.specificity_score * 0.05
            + self.data_quality_score * 0.05
        )
        return round(score, 4)

    @property
    def final_score(self) -> int:
        return min(int(round(self.total_score * 100)), self.score_cap)

    @property
    def score_bucket(self) -> str:
        if self.final_score >= 85:
            return "core"
        if self.final_score >= 70:
            return "important"
        if self.final_score >= 50:
            return "watch"
        return "background" if self.final_score >= 35 else "noise"

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["total_score"] = self.total_score
        data["final_score"] = self.final_score
        data["score_bucket"] = self.score_bucket
        return data


@dataclass_compat(slots=True)
class PriceConfirmation:
    status: str = "unavailable"
    status_zh: str = "数据不足"
    confidence_adjustment: str = "unchanged"
    note: str = "关键价格数据不足，暂时无法确认新闻叙事。"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass_compat(slots=True)
class EventCluster:
    title: str
    category: str
    risk_factor: str
    items: list[ScoredNews]
    primary_assets: list[str]
    secondary_assets: list[str]
    impact_direction: str
    impact_strength: str
    transmission_path: str
    watch_items: list[str]
    final_score: int
    score_bucket: str
    price_confirmation: PriceConfirmation = field(default_factory=PriceConfirmation)
    per_asset_directions: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "category": self.category,
            "risk_factor": self.risk_factor,
            "items": [item.to_dict() for item in self.items],
            "primary_assets": self.primary_assets,
            "secondary_assets": self.secondary_assets,
            "impact_direction": self.impact_direction,
            "impact_strength": self.impact_strength,
            "transmission_path": self.transmission_path,
            "watch_items": self.watch_items,
            "final_score": self.final_score,
            "score_bucket": self.score_bucket,
            "price_confirmation": self.price_confirmation.to_dict(),
            "per_asset_directions": self.per_asset_directions,
        }


@dataclass_compat(slots=True)
class Briefing:
    date: str
    generated_at: str
    core_view: str
    top_news: list[ScoredNews]
    geopolitical_risks: list[str]
    market_environment: list[str]
    watchlist: list[str]
    assumption_change: str
    disclaimer: str
    raw_counts: dict[str, int] = field(default_factory=dict)
    market_points: list[MarketPoint] = field(default_factory=list)
    macro_indicators: list[MacroIndicator] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    market_confidence: str = "medium"
    event_clusters: list[EventCluster] = field(default_factory=list)
    debug_notes: list[str] = field(default_factory=list)
    data_window_start: str = ""
    data_window_end: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "date": self.date,
            "generated_at": self.generated_at,
            "core_view": self.core_view,
            "top_news": [item.to_dict() for item in self.top_news],
            "geopolitical_risks": self.geopolitical_risks,
            "market_environment": self.market_environment,
            "watchlist": self.watchlist,
            "assumption_change": self.assumption_change,
            "disclaimer": self.disclaimer,
            "raw_counts": self.raw_counts,
            "market_points": [point.to_dict() for point in self.market_points],
            "macro_indicators": [indicator.to_dict() for indicator in self.macro_indicators],
            "warnings": self.warnings,
            "market_confidence": self.market_confidence,
            "event_clusters": [cluster.to_dict() for cluster in self.event_clusters],
            "debug_notes": self.debug_notes,
            "data_window_start": self.data_window_start,
            "data_window_end": self.data_window_end,
        }
