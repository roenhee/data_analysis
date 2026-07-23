from __future__ import annotations

import pandas as pd

from data_layer.config import Config
from data_layer.manifest import Manifest
from data_layer.sources import SourceDef
from data_layer.util import content_hash


def _default_query(source: SourceDef, sql: str) -> pd.DataFrame:
    """실 Trino 서버측 집계 실행 (I/O seam; 테스트에서 query_fn으로 대체)."""
    from data_layer.connection import connect

    conn = connect(source)
    try:
        cur = conn.cursor()
        cur.execute(sql)
        rows = cur.fetchall()
        cols = [d[0] for d in cur.description]
        return pd.DataFrame(rows, columns=cols)
    finally:
        conn.close()


def fetch_aggregate(
    config: Config,
    source: SourceDef,
    sql: str,
    refresh: bool = False,
    query_fn=None,
) -> pd.DataFrame:
    """서버측 전수(비샘플) 집계 SQL을 실행하고 결과를 content-hash로 캐시.

    캐시 키는 (sql, source.version())가 결정한다. 성공 시에만 캐시/색인한다.
    query_fn(source, sql) -> DataFrame 로 서버 I/O를 주입할 수 있다.
    """
    config.ensure_dirs()
    h = "agg_" + content_hash(sql, source.version())
    path = config.results_dir / f"{h}.parquet"
    if path.exists() and not refresh:
        return pd.read_parquet(path)

    df = (query_fn or _default_query)(source, sql)
    df.to_parquet(path)

    m = Manifest.load(config.manifest_path)
    m.add_result(
        result_hash=h,
        source_summary=f"{source.id}:aggregate",
        date_range=[],
        params={},
        config_version="",
        rows=int(len(df)),
        size_bytes=int(path.stat().st_size),
    )
    m.save()
    return df
