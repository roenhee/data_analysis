from __future__ import annotations

import json
from pathlib import Path

from data_layer.sources import SourceDef, load_sources


def events_source_from_json(path: Path, source_id: str) -> SourceDef:
    """sources.json에서 특정 소스 정의를 SourceDef로 로드."""
    return load_sources(path)[source_id]


def load_dictionary(path: Path) -> dict:
    """Phase 0 사전 아티팩트(JSON)를 로드."""
    return json.loads(Path(path).read_text())
