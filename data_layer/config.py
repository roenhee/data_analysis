from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Config:
    """캐시 루트와 하위 디렉터리 경로."""

    root: Path

    @property
    def results_dir(self) -> Path:
        return self.root / "results"

    @property
    def config_dir(self) -> Path:
        return self.root / "config"

    @property
    def manifest_path(self) -> Path:
        return self.root / "manifest.json"

    def ensure_dirs(self) -> None:
        for d in (self.results_dir, self.config_dir):
            d.mkdir(parents=True, exist_ok=True)

    @classmethod
    def from_env(cls) -> "Config":
        return cls(root=Path(os.environ.get("DATA_LAYER_CACHE", "cache")))
