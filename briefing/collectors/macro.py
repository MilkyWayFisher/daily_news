from __future__ import annotations

from datetime import datetime, timezone
import time

from briefing.collectors.base import MacroCollector
from briefing.env import first_env
from briefing.http import HttpError, get_json
from briefing.models import MacroIndicator


FRED_SERIES: dict[str, str] = {
    "CPI": "CPIAUCSL",
    "Core CPI": "CPILFESL",
    "PCE": "PCEPI",
    "Core PCE": "PCEPILFE",
    "Unemployment Rate": "UNRATE",
    "Nonfarm Payrolls": "PAYEMS",
    "Initial Jobless Claims": "ICSA",
    "Fed Funds Rate": "FEDFUNDS",
    "10Y Treasury Yield": "DGS10",
    "2Y Treasury Yield": "DGS2",
    "GDP": "GDP",
    "Retail Sales": "RSAFS",
}


class FredMacroCollector(MacroCollector):
    provider_name = "fred"
    endpoint = "https://api.stlouisfed.org/fred/series/observations"

    def collect(self, indicators: list[str], *, lookback_months: int = 6) -> list[MacroIndicator]:
        api_key = first_env("FRED_API_KEY")
        if not api_key:
            return []

        collected: list[MacroIndicator] = []
        for indicator in indicators:
            time.sleep(0.4)
            series_id = FRED_SERIES.get(indicator)
            if not series_id:
                continue
            params = {
                "series_id": series_id,
                "api_key": api_key,
                "file_type": "json",
                "sort_order": "desc",
                "limit": max(14, int(lookback_months) + 14),
            }
            try:
                data = get_json(self.endpoint, params=params, timeout=20)
            except HttpError:
                continue
            observations = [
                item
                for item in data.get("observations", []) or []
                if item.get("value") not in {None, "."}
            ]
            if not observations:
                continue
            latest = observations[0]
            previous = observations[1] if len(observations) > 1 else {}
            latest_value = _parse_float(latest.get("value"))
            previous_value = _parse_float(previous.get("value"))
            collected.append(
                MacroIndicator(
                    indicator=indicator,
                    latest_value=latest_value,
                    previous_value=previous_value,
                    release_date=latest.get("date") or "",
                    source="FRED",
                    interpretation=_interpret(indicator, latest_value, previous_value),
                    raw={
                        "series_id": series_id,
                        "latest": latest,
                        "previous": previous,
                        "observations": observations,
                    },
                )
            )
        return collected


def unavailable_macro(indicators: list[str], reason: str) -> list[MacroIndicator]:
    return [
        MacroIndicator(
            indicator=indicator,
            latest_value=None,
            previous_value=None,
            release_date="",
            source="unavailable",
            interpretation=reason,
            available=False,
        )
        for indicator in indicators
    ]


def _parse_float(value: str | None) -> float | None:
    if value in {None, "", "."}:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _interpret(indicator: str, latest: float | None, previous: float | None) -> str:
    if latest is None:
        return "数据暂不可用。"
    if previous is None:
        return "有最新值，但缺少可比前值。"
    delta = latest - previous
    if abs(delta) < 1e-9:
        return "较前值基本持平。"
    direction = "上行" if delta > 0 else "下行"
    if indicator in {"CPI", "Core CPI", "PCE", "Core PCE"}:
        return f"较前值{direction}，需要观察通胀路径对利率预期的影响。"
    if indicator in {"10Y Treasury Yield", "2Y Treasury Yield", "Fed Funds Rate"}:
        return f"较前值{direction}，可能影响成长股估值和债券价格。"
    if indicator in {"Unemployment Rate", "Initial Jobless Claims"}:
        return f"较前值{direction}，需要结合就业市场降温或韧性判断。"
    return f"较前值{direction}。"
