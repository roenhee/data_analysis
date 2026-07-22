from __future__ import annotations

import duckdb
import pandas as pd

from data_layer.config import Config
from data_layer.manifest import Manifest
from data_layer.util import content_hash


def run(
    config: Config,
    sql: str,
    params: dict | None = None,
    source_version: str = "",
    config_version: str = "",
    source_summary: str = "",
    date_range: list | None = None,
    refresh: bool = False,
) -> pd.DataFrame:
    """로컬 DuckDB로 sql을 실행하고 결과를 내용 해시로 캐시.

    params/source_version/config_version이 캐시 키에 들어가 무효화가 정확해진다.
    결과 DataFrame은 호출자가 만든 그대로 저장된다 (카운트+확률 등은 ②의 책임).
    """
    config.ensure_dirs()
    h = content_hash(sql, params or {}, source_version, config_version)
    path = config.results_dir / f"{h}.parquet"

    if path.exists() and not refresh:
        return pd.read_parquet(path)

    con = duckdb.connect()
    try:
        df = con.execute(sql, params or {}).df()
    finally:
        con.close()

    df.to_parquet(path)
    m = Manifest.load(config.manifest_path)
    m.add_result(
        result_hash=h,
        source_summary=source_summary,
        date_range=date_range or [],
        params=params or {},
        config_version=config_version,
        rows=int(len(df)),
        size_bytes=int(path.stat().st_size),
    )
    m.save()
    return df
