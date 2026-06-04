from __future__ import annotations

import json
from pathlib import Path

from briefing.models import Briefing, NewsItem, ScoredNews


class FileStorage:
    def __init__(self, root: str | Path = "data") -> None:
        self.root = Path(root)

    def save(
        self,
        date: str,
        raw_items: list[NewsItem],
        scored_items: list[ScoredNews],
        briefing: Briefing,
        markdown: str,
    ) -> Path:
        raw_dir = self.root / "raw"
        processed_dir = self.root / "processed"
        briefs_dir = self.root / "briefs"
        debug_dir = self.root / "debug"
        legacy_dir = self.root / date

        for directory in (raw_dir, processed_dir, briefs_dir, debug_dir, legacy_dir):
            directory.mkdir(parents=True, exist_ok=True)

        raw_path = raw_dir / f"{date}-news.json"
        events_path = processed_dir / f"{date}-events.json"
        briefing_json_path = processed_dir / f"{date}-brief.json"
        market_path = processed_dir / f"{date}-market.json"
        macro_path = processed_dir / f"{date}-macro.json"
        brief_path = briefs_dir / f"{date}-brief.md"
        debug_path = debug_dir / f"{date}-debug.md"

        _write_json(raw_path, [item.to_dict() for item in raw_items])
        _write_json(events_path, [item.to_dict() for item in scored_items])
        _write_json(briefing_json_path, briefing.to_dict())
        _write_json(market_path, [point.to_dict() for point in briefing.market_points])
        _write_json(macro_path, [indicator.to_dict() for indicator in briefing.macro_indicators])
        brief_path.write_text(markdown, encoding="utf-8")
        debug_path.write_text(_debug_markdown(briefing), encoding="utf-8")

        _write_json(legacy_dir / "raw_news.json", [item.to_dict() for item in raw_items])
        _write_json(legacy_dir / "scored_news.json", [item.to_dict() for item in scored_items])
        _write_json(legacy_dir / "briefing.json", briefing.to_dict())
        (legacy_dir / "briefing.md").write_text(markdown, encoding="utf-8")
        (legacy_dir / "debug.md").write_text(_debug_markdown(briefing), encoding="utf-8")
        return brief_path


def _write_json(path: Path, data: object) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _debug_markdown(briefing: Briefing) -> str:
    lines = [
        f"# Debug：{briefing.date}",
        "",
        "## Raw Counts",
    ]
    lines.extend([f"- {key}: {value}" for key, value in briefing.raw_counts.items()])
    lines.extend(["", "## Debug Notes"])
    lines.extend([f"- {note}" for note in briefing.debug_notes] or ["- 无"])
    lines.extend(["", "## Event Clusters"])
    for cluster in briefing.event_clusters:
        lines.append(f"- {cluster.title}: {cluster.final_score}, {cluster.risk_factor}, {cluster.price_confirmation.status}")
    lines.append("")
    return "\n".join(lines)
