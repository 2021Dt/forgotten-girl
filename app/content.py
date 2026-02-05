from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List


@dataclass(frozen=True)
class ContentBundle:
    events: List[Dict[str, Any]]
    hooks: List[Dict[str, Any]]
    endings: List[Dict[str, Any]]


def load_json_files(directory: Path) -> List[Dict[str, Any]]:
    if not directory.exists():
        return []
    items: List[Dict[str, Any]] = []
    for path in sorted(directory.glob("*.json")):
        items.append(json.loads(path.read_text(encoding="utf-8")))
    return items


def load_content(root: Path) -> ContentBundle:
    events = load_json_files(root / "content" / "events")
    hooks = load_json_files(root / "content" / "hooks")
    endings = load_json_files(root / "content" / "endings")
    return ContentBundle(events=events, hooks=hooks, endings=endings)
