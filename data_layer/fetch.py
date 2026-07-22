from __future__ import annotations

import duckdb
import pandas as pd

from data_layer.config import Config
from data_layer.manifest import Manifest
from data_layer.util import content_hash, day_strings


def missing_start_days(existing: set[str], start: str, end: str) -> list[str]:
    return [d for d in day_strings(start, end) if d not in existing]


def _partition_path(config: Config, start_day: str):
    return config.events_dir / f"start_day={start_day}.parquet"


def read_partitions(config: Config, days: list[str]) -> pd.DataFrame:
    paths = [str(_partition_path(config, d)) for d in days if _partition_path(config, d).exists()]
    if not paths:
        return pd.DataFrame()
    con = duckdb.connect()
    try:
        return con.execute(
            "SELECT * FROM read_parquet($paths)", {"paths": paths}
        ).df()
    finally:
        con.close()


def get_events(
    config: Config,
    source_id: str,
    source_version: str,
    start: str,
    end: str,
    partition_fetcher,
    sample: dict,
    refresh: bool = False,
) -> pd.DataFrame:
    """[start, end]에 개시된 개체의 원본 이벤트를 반환. 빠진 start_day만 fetch.

    partition_fetcher(start_day) -> DataFrame: 해당 start_day에 개시된 개체를
    개체-완결 샘플로 서버에서 가져온다 (서버 I/O seam, 테스트에서 주입).
    """
    config.ensure_dirs()
    m = Manifest.load(config.manifest_path)
    existing = set() if refresh else m.event_start_days()
    to_fetch = missing_start_days(existing, start, end)

    for day in to_fetch:
        df = partition_fetcher(day)
        path = _partition_path(config, day)
        df.to_parquet(path)
        m.add_event_partition(
            start_day=day,
            entities=int(df["app_user_id"].nunique()) if len(df) else 0,
            rows=int(len(df)),
            size_bytes=int(path.stat().st_size),
            source_id=source_id,
            source_query_hash=content_hash(source_version, day, sample),
            sample=sample,
            window_bounds=[start, end],
        )
    if to_fetch:
        m.save()

    return read_partitions(config, day_strings(start, end))
