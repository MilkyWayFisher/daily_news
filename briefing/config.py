from __future__ import annotations

import json
from dataclasses import asdict, field
from pathlib import Path
from typing import Any

from briefing.compat import dataclass_compat


@dataclass_compat(slots=True)
class UserProfile:
    investment_style: str = "long-term ETF investor"
    risk_tolerance: str = "medium"
    language: str = "zh-CN"


@dataclass_compat(slots=True)
class Watchlist:
    tickers: list[str] = field(default_factory=lambda: ["VOO", "QQQ", "TLT", "GLD", "XLE"])


@dataclass_compat(slots=True)
class Topics:
    macro: list[str] = field(default_factory=list)
    geopolitics: list[str] = field(default_factory=list)
    sectors: list[str] = field(default_factory=list)

    @property
    def all_terms(self) -> list[str]:
        return self.macro + self.geopolitics + self.sectors


@dataclass_compat(slots=True)
class SourceSettings:
    newsapi: bool = True
    gdelt: bool = True
    alphavantage_news: bool = True
    alphavantage_market: bool = True
    rss: bool = True
    fred_macro: bool = True
    max_articles_per_source: int = 30
    lookback_hours: int = 24
    news_lookback_hours: int = 24
    rss_feeds: list[str] = field(
        default_factory=lambda: [
            "https://feeds.a.dj.com/rss/RSSMarketsMain.xml",
            "https://www.cnbc.com/id/100003114/device/rss/rss.html",
            "https://feeds.bbci.co.uk/news/business/rss.xml",
        ]
    )


@dataclass_compat(slots=True)
class MarketSettings:
    market_lookback_days: int = 5
    symbols: list[str] = field(
        default_factory=lambda: [
            "VOO",
            "SPY",
            "QQQ",
            "NVDA",
            "AAPL",
            "MSFT",
            "TSLA",
            "TLT",
            "GLD",
            "XLE",
            "USO",
            "VIX",
            "DXY",
            "WTI",
            "GOLD",
        ]
    )


@dataclass_compat(slots=True)
class MacroSettings:
    macro_lookback_months: int = 6
    indicators: list[str] = field(
        default_factory=lambda: [
            "CPI",
            "Core CPI",
            "PCE",
            "Core PCE",
            "Unemployment Rate",
            "Nonfarm Payrolls",
            "Initial Jobless Claims",
            "Fed Funds Rate",
            "10Y Treasury Yield",
            "2Y Treasury Yield",
            "GDP",
            "Retail Sales",
        ]
    )


@dataclass_compat(slots=True)
class EmailSettings:
    subject_prefix: str = "每日投资情报简报"


@dataclass_compat(slots=True)
class DeliverySettings:
    channel: str = "telegram"
    send_time: str = "08:00"
    timezone: str = "America/Chicago"
    email: EmailSettings = field(default_factory=EmailSettings)


@dataclass_compat(slots=True)
class Rules:
    prohibit_direct_trade_instruction: bool = True
    include_sources: bool = True
    save_history: bool = True
    max_news_items: int = 8
    min_score: float = 50.0
    asset_mapping_path: str = "config/asset_mapping.yaml"


@dataclass_compat(slots=True)
class AppConfig:
    user_profile: UserProfile = field(default_factory=UserProfile)
    watchlist: Watchlist = field(default_factory=Watchlist)
    topics: Topics = field(default_factory=Topics)
    sources: SourceSettings = field(default_factory=SourceSettings)
    market: MarketSettings = field(default_factory=MarketSettings)
    macro: MacroSettings = field(default_factory=MacroSettings)
    delivery: DeliverySettings = field(default_factory=DeliverySettings)
    rules: Rules = field(default_factory=Rules)


def default_config() -> AppConfig:
    return AppConfig(
        topics=Topics(
            macro=[
                "Federal Reserve",
                "inflation",
                "CPI",
                "PCE",
                "Treasury yields",
                "unemployment",
            ],
            geopolitics=[
                "US China",
                "Taiwan Strait",
                "Middle East",
                "Russia Ukraine",
                "sanctions",
                "tariffs",
                "oil supply",
            ],
            sectors=["AI", "semiconductors", "cloud computing", "energy", "banking"],
        ),
        watchlist=Watchlist(["VOO", "QQQ", "NVDA", "AAPL", "MSFT", "TSLA", "TLT", "GLD", "XLE"]),
    )


def load_config(path: str | Path | None = None) -> AppConfig:
    if path is None:
        for candidate in (Path("config.yaml"), Path("config.yml"), Path("config.json")):
            if candidate.exists():
                path = candidate
                break
        else:
            return default_config()

    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")

    data = _load_structured_file(path)
    return config_from_mapping(data)


def _load_structured_file(path: Path) -> dict[str, Any]:
    suffix = path.suffix.lower()
    text = path.read_text(encoding="utf-8")
    if suffix == ".json":
        return json.loads(text)
    if suffix in {".yaml", ".yml"}:
        try:
            import yaml  # type: ignore
        except ImportError as exc:
            raise RuntimeError(
                "YAML config requires PyYAML. Install requirements.txt or use config.example.json."
            ) from exc
        loaded = yaml.safe_load(text)
        return loaded or {}
    raise ValueError(f"Unsupported config format: {path.suffix}")


def config_from_mapping(data: dict[str, Any]) -> AppConfig:
    base = default_config()
    delivery = _delivery_from_mapping(data.get("delivery", {}), base.delivery)
    source_data = dict(data.get("sources", {}))
    if "news_lookback_hours" not in source_data and "lookback_hours" in source_data:
        source_data["news_lookback_hours"] = source_data["lookback_hours"]
    if "news_lookback_hours" in data:
        source_data["news_lookback_hours"] = data["news_lookback_hours"]
    market_data = dict(data.get("market", {}))
    if "market_lookback_days" in data:
        market_data["market_lookback_days"] = data["market_lookback_days"]
    macro_data = dict(data.get("macro", {}))
    if "macro_lookback_months" in data:
        macro_data["macro_lookback_months"] = data["macro_lookback_months"]
    return AppConfig(
        user_profile=UserProfile(**{**asdict(base.user_profile), **data.get("user_profile", {})}),
        watchlist=Watchlist(**{**asdict(base.watchlist), **data.get("watchlist", {})}),
        topics=Topics(**{**asdict(base.topics), **data.get("topics", {})}),
        sources=SourceSettings(**{**asdict(base.sources), **source_data}),
        market=MarketSettings(**{**asdict(base.market), **market_data}),
        macro=MacroSettings(**{**asdict(base.macro), **macro_data}),
        delivery=delivery,
        rules=Rules(**{**asdict(base.rules), **data.get("rules", {})}),
    )


def _delivery_from_mapping(data: dict[str, Any], base: DeliverySettings) -> DeliverySettings:
    email_data = data.get("email", {})
    delivery_data = {**asdict(base), **data}
    delivery_data["email"] = EmailSettings(**{**asdict(base.email), **email_data})
    return DeliverySettings(**delivery_data)
