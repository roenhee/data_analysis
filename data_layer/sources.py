from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

from data_layer.util import content_hash


@dataclass
class SourceDef:
    """하나의 데이터 소스 선언. 접속·테이블·컬럼 매핑을 config로 표현."""

    id: str
    kind: str
    host: str
    port: int
    catalog: str
    schema: str
    table: str
    auth_ref: str
    column_map: dict = field(default_factory=dict)
    filters: list = field(default_factory=list)

    def version(self) -> str:
        return content_hash(
            self.id,
            self.kind,
            self.host,
            self.port,
            self.catalog,
            self.schema,
            self.table,
            self.auth_ref,
            sorted(self.column_map.items()),
            list(self.filters),
        )


def load_sources(path: Path) -> dict[str, SourceDef]:
    raw = json.loads(Path(path).read_text())
    return {d["id"]: SourceDef(**d) for d in raw}


def resolve_auth(source: SourceDef) -> tuple[str, str]:
    """auth_ref 접두어로 환경변수 `<REF>_ID`, `<REF>_PW`를 읽는다."""
    user = os.environ[f"{source.auth_ref}_ID"]
    password = os.environ[f"{source.auth_ref}_PW"]
    return user, password
