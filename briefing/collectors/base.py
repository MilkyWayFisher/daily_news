from __future__ import annotations

from abc import ABC, abstractmethod

from briefing.config import AppConfig
from briefing.models import MacroIndicator, MarketPoint, NewsItem


class NewsCollector(ABC):
    provider_name: str

    @abstractmethod
    def collect(self, config: AppConfig) -> list[NewsItem]:
        raise NotImplementedError


class MarketCollector(ABC):
    provider_name: str

    @abstractmethod
    def collect(self, symbols: list[str]) -> list[MarketPoint]:
        raise NotImplementedError


class MacroCollector(ABC):
    provider_name: str

    @abstractmethod
    def collect(self, indicators: list[str]) -> list[MacroIndicator]:
        raise NotImplementedError
