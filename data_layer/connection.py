from __future__ import annotations

import trino
from trino.auth import BasicAuthentication

from data_layer.sources import SourceDef, resolve_auth


def trino_connect_params(source: SourceDef, user: str, password: str) -> dict:
    return dict(
        host=source.host,
        port=source.port,
        user=user,
        auth=BasicAuthentication(user, password),
        http_scheme="https",
        catalog=source.catalog,
        schema=source.schema,
    )


def connect(source: SourceDef):
    """SourceDef로부터 Trino DBAPI 커넥션을 연다 (실 접속)."""
    user, password = resolve_auth(source)
    return trino.dbapi.connect(**trino_connect_params(source, user, password))
