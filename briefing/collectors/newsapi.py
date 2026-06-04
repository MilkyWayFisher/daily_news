from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

from briefing.collectors.base import NewsCollector
from briefing.config import AppConfig
from briefing.http import HttpError, get_json
from briefing.models import NewsItem


class NewsApiCollector(NewsCollector):
    provider_name = "newsapi"
    endpoint = "https://newsapi.org/v2/everything"

    def collect(self, config: AppConfig) -> list[NewsItem]:
        api_key = os.getenv("NEWSAPI_KEY")
        if not api_key:
            return []

        query_terms = _query_terms(config)
        from_time = datetime.now(timezone.utc) - timedelta(hours=config.sources.news_lookback_hours)
        params = {
            "q": " OR ".join(query_terms[:12]),
            "language": "en",
            "sortBy": "publishedAt",
            "pageSize": min(config.sources.max_articles_per_source, 100),
            "from": from_time.isoformat(timespec="seconds").replace("+00:00", "Z"),
            "apiKey": api_key,
        }
        try:
            data = get_json(self.endpoint, params=params)
        except HttpError:
            return []

        items: list[NewsItem] = []
        for article in data.get("articles", []) or []:
            source = article.get("source") or {}
            title = article.get("title") or ""
            url = article.get("url") or ""
            if not title or not url:
                continue
            items.append(
                NewsItem(
                    title=title,
                    source=source.get("name") or "NewsAPI",
                    url=url,
                    published_at=article.get("publishedAt") or "",
                    summary=article.get("description") or "",
                    raw_content=article.get("content") or "",
                    language="en",
                    source_type="news",
                    metadata={"provider": self.provider_name},
                )
            )
        return items


def _query_terms(config: AppConfig) -> list[str]:
    terms = list(dict.fromkeys(config.watchlist.tickers + config.topics.all_terms))
    if not terms:
        return ["stock market", "Federal Reserve", "technology"]
    return terms
