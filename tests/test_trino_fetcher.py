import pandas as pd

from data_layer.sources import SourceDef
from data_layer.trino_fetcher import TrinoEventFetcher


def _src():
    return SourceDef(
        id="events", kind="trino", host="h", port=8443,
        catalog="bigdata_omega_common_iceberg", schema="axz_tiara", table="all_tiara_i",
        auth_ref="TIARA",
        column_map={"action_name": "action.name", "app_user_id": "user.app_user_id",
                    "isuid": "user.isuid", "day": "date.day"},
        filters=["action.type IN ('Pageview')"],
    )


class FakeCursor:
    def __init__(self, log):
        self._log = log
        self._desc = None
        self._rows = []

    def execute(self, sql):
        self._log.append(sql)
        if sql.strip().upper().startswith("SELECT * FROM") and "start_day = DATE" in sql:
            self._desc = [("app_user_id",), ("isuid",), ("day",), ("start_day",)]
            self._rows = [("u1", "s1", "2026-01-06", "2026-01-06")]
        else:
            self._desc = None
            self._rows = []

    @property
    def description(self):
        return self._desc

    def fetchall(self):
        return self._rows


class FakeConn:
    def __init__(self):
        self.log = []

    def cursor(self):
        return FakeCursor(self.log)


def test_prepare_once_then_partition_then_drop():
    conn = FakeConn()
    with TrinoEventFetcher(
        source=_src(), conn=conn, write_schema="hadoop_rabbit_iceberg.axz_da",
        window=("2026-01-05", "2026-02-01"), seed=7, target_rows=1_000_000,
        table_prefix="roen_dl",
    ) as tf:
        df1 = tf.partition("2026-01-06")
        df2 = tf.partition("2026-01-07")
        assert isinstance(df1, pd.DataFrame)
        assert list(df1.columns) == ["app_user_id", "isuid", "day", "start_day"]
        assert len(df1) == 1

    assert conn.log[0].startswith("CREATE OR REPLACE TABLE hadoop_rabbit_iceberg.axz_da.roen_dl")
    assert sum(1 for s in conn.log if s.startswith("CREATE OR REPLACE TABLE")) == 1
    assert sum(1 for s in conn.log if "start_day = DATE" in s) == 2
    assert any(s.startswith("DROP TABLE IF EXISTS hadoop_rabbit_iceberg.axz_da.roen_dl") for s in conn.log)


def test_drop_runs_even_on_exception():
    conn = FakeConn()
    try:
        with TrinoEventFetcher(
            source=_src(), conn=conn, write_schema="hadoop_rabbit_iceberg.axz_da",
            window=("2026-01-05", "2026-02-01"), seed=1, target_rows=10, table_prefix="roen_dl",
        ) as tf:
            tf.partition("2026-01-06")
            raise RuntimeError("boom")
    except RuntimeError:
        pass
    assert any(s.startswith("DROP TABLE IF EXISTS") for s in conn.log)
