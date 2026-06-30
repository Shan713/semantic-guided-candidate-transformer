from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from src.core.constants import CONFIG_DIR


def _load_yaml_file(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    if not isinstance(data, dict):
        raise ValueError(f"Configuration file must contain a mapping: {path}")
    return data


@lru_cache(maxsize=1)
def load_transformation_config_bundle(config_dir: str | Path | None = None) -> dict[str, Any]:
    base_dir = Path(config_dir) if config_dir is not None else CONFIG_DIR
    return {
        "fusion": _load_yaml_file(base_dir / "fusion.yml"),
        "confidence": _load_yaml_file(base_dir / "confidence.yml"),
        "source_reliability": _load_yaml_file(base_dir / "source_reliability.yml"),
    }
