from __future__ import annotations

from collections import Counter, defaultdict

from briefing.models import ScoredNews


def apply_output_guardrails(
    items: list[ScoredNews],
    *,
    market_confidence: str = "medium",
) -> tuple[list[ScoredNews], list[str]]:
    warnings: list[str] = []
    checked: list[ScoredNews] = []

    path_counts = Counter(item.transmission_path for item in items if item.transmission_path)
    seen_paths: Counter[str] = Counter()
    geo_assets: dict[tuple[str, ...], int] = defaultdict(int)

    for item in items:
        if item.freshness_hours is not None and item.freshness_hours > 168:
            warnings.append(f"已剔除超过 7 天的旧新闻：{item.item.title}")
            continue
        if item.freshness_hours is not None and item.freshness_hours > 36:
            item.score_cap = min(item.score_cap, 60)
        if item.freshness_hours is not None and item.freshness_hours > 72:
            item.score_cap = min(item.score_cap, 40)
        if item.mapping_quality == "none" and item.final_score >= 65:
            item.score_cap = min(item.score_cap, 50)
        if market_confidence == "low" and item.final_score >= 85:
            item.score_cap = min(item.score_cap, 84)
        if item.transmission_path and path_counts[item.transmission_path] >= 3:
            if seen_paths[item.transmission_path] >= 2:
                item.score_cap = min(item.score_cap, 49)
            else:
                item.score_cap = min(item.score_cap, 75)
            seen_paths[item.transmission_path] += 1
            warnings.append("检测到重复影响路径，已将第 3 条及之后的重复事件移出重点事件。")
        if item.category == "geopolitics":
            asset_key = tuple(sorted(item.primary_assets + item.secondary_assets))
            geo_assets[asset_key] += 1
            if _is_tech_only_geopolitics(item):
                item.score_cap = min(item.score_cap, 55)
                warnings.append(f"地缘政治事件缺少明确科技传导路径，已降级：{item.item.title}")
        checked.append(item)

    if any(count >= 3 for count in geo_assets.values()):
        warnings.append("检测到多条地缘政治事件映射到同一资产组合，请复核传导路径。")
    return checked, list(dict.fromkeys(warnings))


def _is_tech_only_geopolitics(item: ScoredNews) -> bool:
    tech_assets = {"QQQ", "NVDA", "AAPL", "TSLA", "MSFT", "AMD", "SMH", "SOXX"}
    assets = set(item.primary_assets + item.secondary_assets)
    if not assets:
        return False
    return assets.issubset(tech_assets) and item.risk_factor not in {"semiconductors", "trade_policy"}
