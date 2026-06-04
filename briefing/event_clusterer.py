from __future__ import annotations

from collections import Counter, defaultdict
import re

from briefing.models import EventCluster, MacroIndicator, MarketPoint, ScoredNews
from briefing.price_confirmation import confirm_price_action


def cluster_events(
    items: list[ScoredNews],
    market_points: list[MarketPoint],
    macro_indicators: list[MacroIndicator],
    *,
    max_clusters: int = 8,
) -> tuple[list[EventCluster], dict[str, int]]:
    groups: dict[tuple[str, str], list[ScoredNews]] = defaultdict(list)
    for item in items:
        groups[_cluster_key(item)].append(item)

    clusters = [
        _build_cluster(group, market_points, macro_indicators)
        for group in groups.values()
        if group
    ]
    clusters.sort(key=lambda cluster: cluster.final_score, reverse=True)

    selected: list[EventCluster] = []
    risk_counts: Counter[str] = Counter()
    for cluster in clusters:
        if cluster.final_score < 55:
            continue
        if risk_counts[cluster.risk_factor] >= 2:
            continue
        selected.append(cluster)
        risk_counts[cluster.risk_factor] += 1
        if len(selected) >= max_clusters:
            break

    stats = {
        "input_events": len(items),
        "cluster_count": len(selected),
        "merged_events": max(0, len(items) - len(selected)),
    }
    return selected, stats


def _cluster_key(item: ScoredNews) -> tuple[str, str]:
    text = _item_text(item)
    if item.risk_factor in {"company_specific", "musk_ecosystem"}:
        return item.risk_factor, (item.primary_assets[0] if item.primary_assets else item.item.title)
    if item.risk_factor == "geopolitics_war":
        return item.risk_factor, _geopolitical_story_key(text)
    if item.risk_factor == "oil_supply":
        return item.risk_factor, _oil_story_key(text)
    if item.risk_factor == "trade_policy":
        return item.risk_factor, _policy_story_key(text)
    if item.risk_factor in {"semiconductors", "rates", "inflation"}:
        return item.risk_factor, item.risk_factor
    primary = ",".join(item.primary_assets[:2]) if item.primary_assets else item.risk_factor
    return item.risk_factor, primary


def _build_cluster(
    items: list[ScoredNews],
    market_points: list[MarketPoint],
    macro_indicators: list[MacroIndicator],
) -> EventCluster:
    ordered = sorted(items, key=lambda item: item.final_score, reverse=True)
    leader = ordered[0]
    primary = _merge_lists(item.primary_assets for item in ordered)
    secondary = [asset for asset in _merge_lists(item.secondary_assets for item in ordered) if asset not in primary]
    watch_items = _merge_lists(item.watch_items for item in ordered)
    transmission_path = _select_transmission_path(ordered)
    per_asset_directions = _merge_asset_directions(ordered)
    price_confirmation = confirm_price_action(leader.risk_factor, primary, market_points, macro_indicators)
    final_score = _cluster_score(ordered, price_confirmation.status)
    return EventCluster(
        title=_cluster_title(leader, primary),
        category=_majority([item.category for item in ordered]),
        risk_factor=leader.risk_factor,
        items=ordered,
        primary_assets=primary,
        secondary_assets=secondary,
        impact_direction=_aggregate_direction([item.impact_direction for item in ordered]),
        impact_strength=_aggregate_strength([item.impact_strength for item in ordered]),
        transmission_path=transmission_path,
        watch_items=watch_items,
        final_score=final_score,
        score_bucket=_score_bucket(final_score),
        price_confirmation=price_confirmation,
        per_asset_directions=per_asset_directions,
    )


def _cluster_score(items: list[ScoredNews], price_status: str) -> int:
    base = round((items[0].final_score * 0.65) + (_average([item.final_score for item in items[:3]]) * 0.35))
    risk_factor = items[0].risk_factor
    categories = {item.category for item in items}

    if risk_factor == "company_specific" and not (categories & {"earnings", "policy"}):
        base = min(base, 70)
    if risk_factor == "musk_ecosystem":
        base = min(base, 65)
    if risk_factor == "semiconductors":
        base = min(max(base, 68), 80)
    if risk_factor in {"oil_supply", "geopolitics_war"} and price_status != "short_price_sync":
        base = min(base, 78)
    if risk_factor == "trade_policy" and len(items[0].primary_assets) <= 2:
        base = min(base, 65)

    if price_status == "short_price_sync":
        base += 2
    elif price_status == "short_price_divergence":
        base -= 8
    elif price_status == "unavailable":
        base = min(base, 72)
    elif price_status == "unconfirmed":
        base = min(base, 78)

    return max(0, min(100, base))


def _cluster_title(item: ScoredNews, primary_assets: list[str]) -> str:
    mapping = {
        "oil_supply": "原油与能源供应风险",
        "semiconductors": "半导体与 AI 芯片链条",
        "rates": "利率与美债收益率变化",
        "inflation": "通胀数据与降息预期",
        "trade_policy": "贸易政策与关税不确定性",
        "geopolitics_war": "地缘冲突与避险情绪",
        "soft_commodities": "软商品价格与消费成本",
        "musk_ecosystem": "Elon Musk 关联生态 / 私募估值事件",
    }
    if item.risk_factor == "company_specific" and primary_assets:
        return f"{' / '.join(primary_assets[:2])} 公司事件"
    if item.risk_factor == "geopolitics_war":
        text = _item_text(item)
        if "iran" in text and ("nuclear" in text or "weapon" in text or "uranium" in text):
            return "伊朗核问题与中东风险"
        if "russia" in text or "ukraine" in text:
            return "俄乌局势与制裁风险"
        if "israel" in text or "middle east" in text:
            return "中东局势与避险情绪"
        if "taiwan" in text or "china" in text:
            return "台海 / 中美地缘风险"
    return mapping.get(item.risk_factor, item.item.title)


def _merge_lists(groups: object) -> list[str]:
    merged: list[str] = []
    for group in groups:  # type: ignore[assignment]
        for item in group:
            if item and item not in merged:
                merged.append(item)
    return merged


def _select_transmission_path(items: list[ScoredNews]) -> str:
    counts = Counter(item.transmission_path for item in items if item.transmission_path)
    if counts:
        return counts.most_common(1)[0][0]
    return items[0].reasoning


def _merge_asset_directions(items: list[ScoredNews]) -> dict[str, str]:
    directions: dict[str, str] = {}
    for item in items:
        for asset, direction in item.affected_asset_directions.items():
            current = directions.get(asset)
            if current is None:
                directions[asset] = direction
            elif current != direction:
                directions[asset] = "mixed"
    return directions


def _aggregate_direction(directions: list[str]) -> str:
    values = set(directions)
    if "bearish" in values and "bullish" in values:
        return "mixed"
    if "bearish" in values:
        return "bearish"
    if "bullish" in values:
        return "bullish"
    if "mixed" in values:
        return "mixed"
    return "unclear"


def _aggregate_strength(strengths: list[str]) -> str:
    if "high" in strengths:
        return "high"
    if "medium" in strengths:
        return "medium"
    return "low"


def _majority(values: list[str]) -> str:
    return Counter(values).most_common(1)[0][0] if values else "low_relevance"


def _score_bucket(score: int) -> str:
    if score >= 85:
        return "core"
    if score >= 70:
        return "important"
    if score >= 55:
        return "watch"
    return "background"


def _average(values: list[int]) -> float:
    return sum(values) / len(values) if values else 0.0


def _item_text(item: ScoredNews) -> str:
    return f"{item.item.title} {item.item.summary} {item.item.raw_content}".lower()


def _geopolitical_story_key(text: str) -> str:
    if "iran" in text and ("nuclear" in text or "weapon" in text or "uranium" in text):
        return "iran_nuclear"
    if "iran" in text or "hormuz" in text:
        return "iran_middle_east"
    if "israel" in text or "middle east" in text:
        return "middle_east"
    if "russia" in text or "ukraine" in text:
        return "russia_ukraine"
    if "taiwan" in text or "china" in text:
        return "taiwan_china"
    return _title_fingerprint(text)


def _oil_story_key(text: str) -> str:
    if "hormuz" in text or "middle east" in text or "shipping" in text:
        return "oil_middle_east_shipping"
    if "russia" in text or "sanction" in text:
        return "oil_russia_sanctions"
    if "opec" in text:
        return "oil_opec"
    return "oil_supply"


def _policy_story_key(text: str) -> str:
    if "export control" in text or "advanced chip" in text or "ai chip" in text:
        return "chip_export_controls"
    if "tariff" in text or "tariffs" in text:
        return "tariffs"
    if "sanction" in text or "sanctions" in text:
        return "sanctions"
    return _title_fingerprint(text)


def _title_fingerprint(text: str) -> str:
    words = [
        word
        for word in re.findall(r"[a-z0-9]+", text)
        if len(word) > 3 and word not in {"says", "would", "with", "from", "that", "this", "after", "before"}
    ]
    return "_".join(words[:4]) or "misc"
