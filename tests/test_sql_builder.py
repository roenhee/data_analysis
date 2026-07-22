from data_layer.sources import SourceDef
from data_layer.sql_builder import (
    build_prepare_sql,
    build_partition_sql,
    build_action_counts_sql,
)


def _src():
    return SourceDef(
        id="events", kind="trino",
        host="h", port=8443,
        catalog="bigdata_omega_common_iceberg", schema="axz_tiara", table="all_tiara_i",
        auth_ref="TIARA",
        column_map={
            "action_name": "action.name",
            "app_user_id": "user.app_user_id",
            "isuid": "user.isuid",
            "access_time": "try_cast(common.access_time AS timestamp)",
            "day": "date.day",
        },
        filters=[
            "action.type IN ('Pageview')",
            "NULLIF(TRIM(user.app_user_id), '') IS NOT NULL",
        ],
    )


def test_prepare_sql_has_core_pieces():
    sql = build_prepare_sql(
        _src(),
        temp_table="hadoop_rabbit_iceberg.axz_da.roen_dl_abc_sampled",
        window=("2026-01-05", "2026-02-01"),
        seed=7,
        target_rows=1_000_000,
    )
    assert "bigdata_omega_common_iceberg.axz_tiara.all_tiara_i" in sql
    assert "CREATE OR REPLACE TABLE hadoop_rabbit_iceberg.axz_da.roen_dl_abc_sampled AS" in sql
    assert "action.name AS action_name" in sql
    assert "user.app_user_id AS app_user_id" in sql
    assert "action.type IN ('Pageview')" in sql
    assert "random()" not in sql
    assert "md5" in sql and "7" in sql
    assert "start_day" in sql
    assert "2026-01-05" in sql and "2026-02-01" in sql
    assert "1000000" in sql


def test_partition_sql_filters_by_day():
    sql = build_partition_sql("hadoop_rabbit_iceberg.axz_da.roen_dl_abc_sampled", "2026-01-06")
    assert "SELECT * FROM hadoop_rabbit_iceberg.axz_da.roen_dl_abc_sampled" in sql
    assert "start_day = DATE '2026-01-06'" in sql


def test_action_counts_sql():
    sql = build_action_counts_sql(_src(), ("2026-01-05", "2026-02-01"))
    assert "bigdata_omega_common_iceberg.axz_tiara.all_tiara_i" in sql
    assert "action.name AS action_name" in sql
    assert "COUNT(*)" in sql
    assert "GROUP BY" in sql


def test_start_day_is_date_typed_consistent_with_partition_filter():
    src = _src()
    prep = build_prepare_sql(
        src, temp_table="cat.sch.t_sampled",
        window=("2026-01-05", "2026-02-01"), seed=1, target_rows=100,
    )
    # start_day must be a DATE column (not cast to varchar), so it can be
    # compared against the DATE literal used by build_partition_sql.
    assert "AS varchar) AS start_day" not in prep
    assert "date(min(_access_ts)) AS start_day" in prep
    part = build_partition_sql("cat.sch.t_sampled", "2026-01-06")
    assert "start_day = DATE '2026-01-06'" in part
