from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict

import yaml


@dataclass(frozen=True)
class ConfigBundle:
    run: Dict[str, Any]
    resources: Dict[str, Any]
    caps: Dict[str, Any]
    pity: Dict[str, Any]


def load_yaml(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def load_config(root: Path) -> ConfigBundle:
    return ConfigBundle(
        run=load_yaml(root / "config" / "run.yaml"),
        resources=load_yaml(root / "config" / "resources.yaml"),
        caps=load_yaml(root / "config" / "caps.yaml"),
        pity=load_yaml(root / "config" / "pity.yaml"),
    )
