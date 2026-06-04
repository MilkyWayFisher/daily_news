from __future__ import annotations

import os
import urllib.parse
import urllib.request


class TelegramDelivery:
    def __init__(self) -> None:
        self.bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "")
        self.chat_id = os.getenv("TELEGRAM_CHAT_ID", "")

    @property
    def configured(self) -> bool:
        return bool(self.bot_token and self.chat_id)

    def send_markdown(self, markdown: str) -> bool:
        if not self.configured:
            return False
        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        chunks = _split_message(markdown, limit=3900)
        success = True
        for chunk in chunks:
            data = urllib.parse.urlencode(
                {
                    "chat_id": self.chat_id,
                    "text": chunk,
                    "disable_web_page_preview": "true",
                }
            ).encode("utf-8")
            request = urllib.request.Request(url, data=data, method="POST")
            try:
                with urllib.request.urlopen(request, timeout=20) as response:
                    success = success and 200 <= response.status < 300
            except OSError:
                success = False
        return success


def _split_message(text: str, limit: int) -> list[str]:
    if len(text) <= limit:
        return [text]
    chunks: list[str] = []
    current: list[str] = []
    current_len = 0
    for line in text.splitlines():
        parts = _split_long_line(line, limit)
        for part in parts:
            if len(part) >= limit:
                if current:
                    chunks.append("\n".join(current))
                    current = []
                    current_len = 0
                chunks.append(part)
                continue

            extra = len(part) + 1
            if current and current_len + extra > limit:
                chunks.append("\n".join(current))
                current = []
                current_len = 0
            current.append(part)
            current_len += extra
    if current:
        chunks.append("\n".join(current))
    return chunks


def _split_long_line(line: str, limit: int) -> list[str]:
    if len(line) <= limit:
        return [line]
    return [line[index : index + limit] for index in range(0, len(line), limit)]
