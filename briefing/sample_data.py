from __future__ import annotations

from datetime import datetime, timedelta, timezone

from briefing.models import NewsItem


def sample_news() -> list[NewsItem]:
    now = datetime.now(timezone.utc)
    rows = [
        (
            "Treasury yields rise as investors reassess Federal Reserve rate-cut path",
            "Reuters",
            "https://example.com/yields-fed",
            "Higher yields pressured rate-sensitive growth shares while traders waited for more inflation data.",
        ),
        (
            "Major cloud providers expand AI infrastructure spending plans",
            "CNBC",
            "https://example.com/cloud-ai-spending",
            "Large technology firms continue to invest in AI chips and data centers.",
        ),
        (
            "New export control discussion raises uncertainty for advanced AI chips",
            "Financial Times",
            "https://example.com/chip-export-controls",
            "Potential restrictions could affect semiconductor demand and supply chains.",
        ),
        (
            "Oil prices climb after Middle East shipping risk returns to focus",
            "Associated Press",
            "https://example.com/oil-middle-east",
            "Energy markets watched shipping lanes and possible supply disruption.",
        ),
        (
            "Apple shares in focus as analysts debate China demand outlook",
            "Bloomberg",
            "https://example.com/apple-china-demand",
            "China demand remains a key swing factor for large-cap technology earnings expectations.",
        ),
        (
            "Soft inflation report would strengthen case for Federal Reserve patience",
            "MarketWatch",
            "https://example.com/inflation-fed-patience",
            "Investors are watching CPI and PCE data for confirmation of the disinflation path.",
        ),
        (
            "Semiconductor index slips as investors question near-term AI valuation",
            "CNBC",
            "https://example.com/semis-ai-valuation",
            "Chip stocks pulled back as valuation concerns resurfaced.",
        ),
        (
            "Russia Ukraine negotiations remain uncertain as sanctions pressure persists",
            "Reuters",
            "https://example.com/russia-ukraine-sanctions",
            "The sanctions backdrop continues to affect energy and geopolitical risk sentiment.",
        ),
    ]
    items: list[NewsItem] = []
    for index, (title, source, url, summary) in enumerate(rows):
        items.append(
            NewsItem(
                title=title,
                source=source,
                url=url,
                published_at=(now - timedelta(hours=index + 1)).isoformat(timespec="seconds"),
                summary=summary,
                raw_content=summary,
                language="en",
                source_type="news",
                metadata={"provider": "sample"},
            )
        )
    return items
