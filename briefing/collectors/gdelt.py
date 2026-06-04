from __future__ import annotations

import urllib.parse
from datetime import datetime, timedelta, timezone

from briefing.collectors.base import NewsCollector
from briefing.config import AppConfig
from briefing.http import HttpError, get_json
from briefing.models import NewsItem


class GdeltCollector(NewsCollector):
    provider_name = "gdelt"
    endpoint = "https://api.gdeltproject.org/api/v2/doc/doc"

    def collect(self, config: AppConfig) -> list[NewsItem]:
        query = " OR ".join(_query_terms(config)[:15])
        start = datetime.now(timezone.utc) - timedelta(hours=config.sources.news_lookback_hours)
        params = {
            "query": query,
            "mode": "ArtList",
            "format": "json",
            "maxrecords": min(config.sources.max_articles_per_source, 250),
            "sort": "hybridrel",
            "startdatetime": start.strftime("%Y%m%d%H%M%S"),
        }
        try:
            data = get_json(self.endpoint, params=params)
        except HttpError:
            return []

        articles = data.get("articles", []) or []
        items: list[NewsItem] = []
        for article in articles:
            title = article.get("title") or ""
            url = article.get("url") or ""
            if not title or not url:
                continue
            items.append(
                NewsItem(
                    title=title,
                    source=article.get("domain") or "GDELT",
                    url=urllib.parse.unquote(url),
                    published_at=article.get("seendate") or "",
                    summary=article.get("title") or "",
                    raw_content="",
                    language=article.get("language") or "",
                    source_type="news",
                    metadata={"provider": self.provider_name},
                )
            )
        return items


def _query_terms(config: AppConfig) -> list[str]:
    return list(dict.fromkeys(config.watchlist.tickers + config.topics.all_terms))
