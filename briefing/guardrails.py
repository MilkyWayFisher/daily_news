from __future__ import annotations

import re


BANNED_PATTERNS = [
    r"今天买入",
    r"今天卖出",
    r"立即买入",
    r"立即卖出",
    r"立刻买入",
    r"立刻卖出",
    r"必须买入",
    r"必须卖出",
    r"一定上涨",
    r"一定下跌",
    r"必涨",
    r"必跌",
    r"稳赚",
    r"无风险",
    r"抄底",
    r"梭哈",
]

REPLACEMENTS = {
    "今天买入": "今日重点观察",
    "今天卖出": "今日重点观察",
    "立即买入": "需要等待更多确认",
    "立即卖出": "需要等待更多确认",
    "立刻买入": "需要等待更多确认",
    "立刻卖出": "需要等待更多确认",
    "必须买入": "需要结合自身风险承受能力评估",
    "必须卖出": "需要结合自身风险承受能力评估",
    "一定上涨": "可能上行",
    "一定下跌": "可能下行",
    "必涨": "可能偏强",
    "必跌": "可能偏弱",
    "稳赚": "存在不确定性",
    "无风险": "仍有风险",
    "抄底": "低位观察",
    "梭哈": "避免过度集中",
}


def sanitize_text(text: str) -> str:
    cleaned = text
    for banned, replacement in REPLACEMENTS.items():
        cleaned = cleaned.replace(banned, replacement)
    return cleaned


def validate_text(text: str) -> list[str]:
    violations: list[str] = []
    for pattern in BANNED_PATTERNS:
        if re.search(pattern, text):
            violations.append(pattern)
    return violations
