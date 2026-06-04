from __future__ import annotations

import re

from briefing.models import NewsItem


CATEGORIES = {
    "macro",
    "market",
    "geopolitics",
    "company",
    "sector",
    "earnings",
    "policy",
    "commodity",
    "rates",
    "low_relevance",
}


COMPANY_TERMS = (
    "nvidia",
    "nvda",
    "marvell",
    "mrvl",
    "apple",
    "aapl",
    "microsoft",
    "msft",
    "tesla",
    "tsla",
    "amd",
    "broadcom",
    "avgo",
    "spacex",
    "starlink",
    "elon musk",
)

EARNINGS_TERMS = ("earnings", "revenue", "guidance", "eps", "profit", "margin")
SECTOR_TERMS = (
    "semiconductor",
    "semiconductors",
    "ai chips",
    "artificial intelligence",
    "data center",
    "cloud",
    "software",
    "chip demand",
)
RATES_TERMS = (
    "treasury yield",
    "treasury yields",
    "10-year yield",
    "2-year yield",
    "real yields",
    "rate cut",
    "rate hike",
    "fomc",
    "powell",
)
MACRO_TERMS = (
    "federal reserve",
    "inflation",
    "cpi",
    "pce",
    "jobs",
    "unemployment",
    "payrolls",
    "gdp",
    "retail sales",
)
COMMODITY_TERMS = (
    "oil",
    "crude",
    "brent",
    "wti",
    "opec",
    "gold",
    "gas",
    "coffee",
    "coal",
    "commodity",
)
GEOPOLITICS_TERMS = (
    "war",
    "attack",
    "middle east",
    "russia",
    "ukraine",
    "iran",
    "israel",
    "taiwan",
    "shipping disruption",
    "shipping risk",
)
POLICY_TERMS = (
    "tariff",
    "tariffs",
    "sanction",
    "sanctions",
    "export control",
    "export controls",
    "regulation",
    "antitrust",
    "sec",
    "probe",
)
MARKET_TERMS = ("vix", "s&p 500", "nasdaq", "dow", "futures", "selloff", "rally")
LOW_RELEVANCE_BLOCKERS = (
    "coal mine disaster",
    "mine disaster",
    "local accident",
    "coffee prices",
)
ENERGY_SUPPLY_QUALIFIERS = (
    "energy supply",
    "supply shock",
    "coal price spike",
    "power shortage",
    "industrial production",
    "policy response",
)


def classify(item: NewsItem) -> str:
    text = _event_text(item)

    if _is_low_relevance_commodity_accident(text):
        return "low_relevance"
    if _is_low_relevance_us_personnel_event(text):
        return "low_relevance"
    if "spacex" in text or "starlink" in text:
        return "company"
    if _has_any(text, EARNINGS_TERMS) and (_has_any(text, COMPANY_TERMS) or item.symbols):
        return "earnings"
    if _has_any(text, COMPANY_TERMS) and _has_any(text, SECTOR_TERMS + EARNINGS_TERMS):
        return "company"
    if _has_any(text, SECTOR_TERMS):
        return "sector"
    if _has_any(text, RATES_TERMS):
        return "rates"
    if _has_any(text, COMMODITY_TERMS):
        return "commodity"
    if _has_any(text, POLICY_TERMS):
        return "policy"
    if _has_any(text, GEOPOLITICS_TERMS):
        return "geopolitics"
    if _has_any(text, MACRO_TERMS):
        return "macro"
    if _has_any(text, MARKET_TERMS):
        return "market"
    if _has_any(text, COMPANY_TERMS) or item.symbols:
        return "company"
    return "low_relevance"


def _event_text(item: NewsItem) -> str:
    return f"{item.title} {item.summary} {item.raw_content} {' '.join(item.symbols)}".lower()


def _has_any(text: str, terms: tuple[str, ...]) -> bool:
    return any(_contains(text, term) for term in terms)


def _contains(text: str, term: str) -> bool:
    if term.isupper() or len(term) <= 5:
        return bool(re.search(rf"(?<![a-z0-9]){re.escape(term.lower())}(?![a-z0-9])", text))
    return term.lower() in text


def _is_low_relevance_commodity_accident(text: str) -> bool:
    if not _has_any(text, LOW_RELEVANCE_BLOCKERS):
        return False
    return not _has_any(text, ENERGY_SUPPLY_QUALIFIERS)


def _is_low_relevance_us_personnel_event(text: str) -> bool:
    personnel_terms = ("spy chief", "appointment", "appoint", "nomination", "personnel")
    domestic_terms = ("trump", "white house", "congress", "pulte")
    conflict_terms = ("iran", "israel", "russia", "ukraine", "middle east", "sanction", "tariff", "war")
    return (
        any(term in text for term in personnel_terms)
        and any(term in text for term in domestic_terms)
        and not any(term in text for term in conflict_terms)
    )
