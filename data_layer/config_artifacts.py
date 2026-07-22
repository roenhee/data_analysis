from __future__ import annotations

import json
from pathlib import Path

from data_layer.sources import SourceDef, load_sources
from data_layer.util import content_hash


def events_source_from_json(path: Path, source_id: str) -> SourceDef:
    """sources.json에서 특정 소스 정의를 SourceDef로 로드."""
    return load_sources(path)[source_id]


def load_dictionary(path: Path) -> dict:
    """Phase 0 사전 아티팩트(JSON)를 로드."""
    return json.loads(Path(path).read_text())


def config_version(dictionary: dict, sessionization: dict) -> str:
    """사전(dictionary)+세션화 config로부터 안정적 버전 문자열.

    content_hash가 dict 키 순서에 무관하므로 같은 내용이면 같은 버전.
    사전이나 세션화가 바뀌면 버전도 바뀐다.
    """
    return content_hash(dictionary, sessionization)
