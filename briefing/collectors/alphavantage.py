from __future__ import annotations

import os

from briefing.collectors.base import NewsCollector
from briefing.config import AppConfig
from briefing.env import first_env
from briefing.http import HttpError, get_json
from briefing.models import NewsItem


class AlphaVantageNewsCollector(NewsCollector):
    provider_name = "alphavantage_news"
    endpoint = "https://www.alphavantage.co/query"

    def collect(self, config: AppConfig) -> list[NewsItem]:
        api_key = first_env("ALPHAVANTAGE_API_KEY", "ALPHAVANTAGE_KEY")
        if not api_key:
            return []

        params = {
            "function": "NEWS_SENTIMENT",
            "tickers": ",".join(config.watchlist.tickers[:20]),
            "topics": ",".join(_alpha_topics(config)),
            "limit": min(config.sources.max_articles_per_source, 1000),
            "apikey": api_key,
        }
        try:
            data = get_json(self.endpoint, params=params)
        except HttpError:
            return []

        items: list[NewsItem] = []
        for article in data.get("feed", []) or []:
            title = article.get("title") or ""
            url = article.get("url") or ""
            if not title or not url:
                continue
            tickers = [
                ticker.get("ticker", "")
                for ticker in article.get("ticker_sentiment", []) or []
                if ticker.get("ticker")
            ]
            items.append(
                NewsItem(
                    title=title,
                    source=article.get("source") or "Alpha Vantage",
                    url=url,
                    published_at=article.get("time_published") or "",
                    summary=article.get("summary") or "",
                    raw_content=article.get("summary") or "",
                    language="en",
                    source_type="news",
                    symbols=tickers,
                    metadata={
                        "provider": self.provider_name,
                        "overall_sentiment_score": article.get("overall_sentiment_score"),
                        "overall_sentiment_label": article.get("overall_sentiment_label"),
                    },
                )
            )
        return items


def _alpha_topics(config: AppConfig) -> list[str]:
    topic_map = {
        "AI": "technology",
        "semiconductors": "technology",
        "cloud computing": "technology",
        "energy": "energy_transportation",
        "banking": "finance",
        "inflation": "economy_monetary",
        "Federal Reserve": "economy_monetary",
    }
    topics = [topic_map[term] for term in config.topics.all_terms if term in topic_map]
    return list(dict.fromkeys(topics)) or ["technology", "economy_monetary"]
