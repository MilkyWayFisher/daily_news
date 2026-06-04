from __future__ import annotations

from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import xml.etree.ElementTree as ET

from briefing.collectors.base import NewsCollector
from briefing.config import AppConfig
from briefing.http import HttpError
from briefing.models import NewsItem

import urllib.error
import urllib.request


class RssCollector(NewsCollector):
    provider_name = "rss"

    def collect(self, config: AppConfig) -> list[NewsItem]:
        items: list[NewsItem] = []
        for feed_url in config.sources.rss_feeds:
            items.extend(self._collect_feed(feed_url, config.sources.max_articles_per_source))
        return items

    def _collect_feed(self, feed_url: str, limit: int) -> list[NewsItem]:
        try:
            request = urllib.request.Request(
                feed_url,
                headers={"User-Agent": "daily-investment-brief/1.0"},
            )
            with urllib.request.urlopen(request, timeout=20) as response:
                xml_text = response.read()
        except (urllib.error.URLError, TimeoutError, OSError):
            return []

        try:
            root = ET.fromstring(xml_text)
        except ET.ParseError:
            return []

        channel_title = _text(root.find("./channel/title")) or "RSS"
        parsed: list[NewsItem] = []
        for item in root.findall("./channel/item")[:limit]:
            title = _text(item.find("title"))
            link = _text(item.find("link"))
            if not title or not link:
                continue
            published = _parse_date(_text(item.find("pubDate")))
            summary = _text(item.find("description"))
            parsed.append(
                NewsItem(
                    title=title,
                    source=channel_title,
                    url=link,
                    published_at=published,
                    summary=summary,
                    raw_content=summary,
                    language="en",
                    source_type="news",
                    metadata={"provider": self.provider_name, "feed_url": feed_url},
                )
            )
        return parsed


def _text(element: ET.Element | None) -> str:
    return "" if element is None or element.text is None else element.text.strip()


def _parse_date(value: str) -> str:
    if not value:
        return datetime.now(timezone.utc).isoformat(timespec="seconds")
    try:
        parsed = parsedate_to_datetime(value)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc).isoformat(timespec="seconds")
    except (TypeError, ValueError):
        return datetime.now(timezone.utc).isoformat(timespec="seconds")
