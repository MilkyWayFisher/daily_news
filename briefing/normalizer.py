from __future__ import annotations

from datetime import datetime, timezone

from briefing.models import NewsItem


def normalize_items(items: list[NewsItem]) -> list[NewsItem]:
    normalized: list[NewsItem] = []
    for item in items:
        title = " ".join(item.title.split())
        url = item.url.strip()
        if not title or not url:
            continue
        normalized.append(
            NewsItem(
                title=title,
                source=(item.source or "Unknown").strip(),
                url=url,
                published_at=_normalize_datetime(item.published_at),
                summary=" ".join((item.summary or "").split()),
                raw_content=item.raw_content or "",
                language=item.language or "",
                source_type=item.source_type or "news",
                symbols=[symbol.upper() for symbol in item.symbols if symbol],
                entities=list(dict.fromkeys(item.entities)),
                topics=list(dict.fromkeys(item.topics)),
                metadata=item.metadata,
            )
        )
    return normalized


def _normalize_datetime(value: str) -> str:
    if not value:
        return datetime.now(timezone.utc).isoformat(timespec="seconds")
    cleaned = value.strip()

    compact = cleaned[:-1] if cleaned.endswith("Z") else cleaned
    for fmt in ("%Y%m%dT%H%M%S", "%Y%m%d%H%M%S"):
        try:
            parsed = datetime.strptime(compact, fmt).replace(tzinfo=timezone.utc)
            return parsed.isoformat(timespec="seconds")
        except ValueError:
            pass

    if cleaned.endswith("Z"):
        cleaned = cleaned[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(cleaned)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc).isoformat(timespec="seconds")
    except (TypeError, ValueError):
        return value
