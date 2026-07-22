from __future__ import annotations

import logging

import pandas as pd

from data_layer.sources import SourceDef
from data_layer.sql_builder import build_partition_sql, build_prepare_sql
from data_layer.util import content_hash

logger = logging.getLogger(__name__)


class TrinoEventFetcher:
    """배치-prepare 임시테이블 → 조각 pull → 종료 시 DROP.

    `.partition(day)`를 data_layer.fetch.get_events의 partition_fetcher로 넘긴다.
    prepare는 첫 partition 호출 시 1회 지연 실행된다.
    단일 `with` 블록에서 1회만 사용한다 (인스턴스를 여러 `with`에 재사용하지 말 것).
    """

    def __init__(
        self,
        source: SourceDef,
        conn,
        write_schema: str,
        window: tuple[str, str],
        seed: int,
        target_rows: int,
        table_prefix: str = "dl",
    ):
        self.source = source
        self.conn = conn
        self.write_schema = write_schema
        self.window = window
        self.seed = seed
        self.target_rows = target_rows
        tag = content_hash(source.version(), window, seed, target_rows)
        self.temp_table = f"{write_schema}.{table_prefix}_{tag}_sampled"
        self._prepared = False

    def __enter__(self) -> "TrinoEventFetcher":
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        if self._prepared:
            try:
                self.conn.cursor().execute(f"DROP TABLE IF EXISTS {self.temp_table}")
            except Exception as drop_err:  # best-effort; never mask the original exception
                logger.warning(
                    "Failed to drop temp table %s: %s. It may be orphaned on the "
                    "server; run cleanup.drop_temp_tables to sweep it.",
                    self.temp_table, drop_err,
                )
        return False

    def _prepare(self) -> None:
        sql = build_prepare_sql(
            self.source, self.temp_table, self.window, self.seed, self.target_rows
        )
        self.conn.cursor().execute(sql)
        self._prepared = True

    def partition(self, start_day: str) -> pd.DataFrame:
        if not self._prepared:
            self._prepare()
        cur = self.conn.cursor()
        cur.execute(build_partition_sql(self.temp_table, start_day))
        cols = [d[0] for d in cur.description]
        return pd.DataFrame(cur.fetchall(), columns=cols)
