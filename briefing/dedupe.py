from __future__ import annotations

import re
from difflib import SequenceMatcher

from briefing.models import NewsItem


def dedupe_items(items: list[NewsItem], title_threshold: float = 0.88) -> list[NewsItem]:
    selected: list[NewsItem] = []
    seen_urls: set[str] = set()
    for item in sorted(items, key=_source_quality_key, reverse=True):
        normalized_url = _normalize_url(item.url)
        if normalized_url in seen_urls:
            continue
        if any(_title_similarity(item.title, existing.title) >= title_threshold for existing in selected):
            continue
        selected.append(item)
        seen_urls.add(normalized_url)
    return sorted(selected, key=lambda item: item.published_at, reverse=True)


def _source_quality_key(item: NewsItem) -> tuple[int, int, int]:
    authority = _authority_score(item.source)
    detail = len(item.summary or "") + len(item.raw_content or "")
    source_type = 1 if item.source_type in {"official", "market_data"} else 0
    return authority, source_type, detail


def _authority_score(source: str) -> int:
    source_lower = source.lower()
    high_quality = {
        "reuters",
        "associated press",
        "ap",
        "bloomberg",
        "wall street journal",
        "financial times",
        "cnbc",
        "sec",
        "federal reserve",
        "treasury",
        "bls",
        "bea",
        "eia",
    }
    return 2 if any(name in source_lower for name in high_quality) else 1


def _normalize_url(url: str) -> str:
    return url.split("?")[0].rstrip("/").lower()


def _title_similarity(left: str, right: str) -> float:
    return SequenceMatcher(None, _normalize_title(left), _normalize_title(right)).ratio()


def _normalize_title(title: str) -> str:
    cleaned = re.sub(r"[^a-z0-9 ]+", " ", title.lower())
    return " ".join(cleaned.split())
