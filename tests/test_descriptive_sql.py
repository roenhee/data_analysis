from data_layer.sources import SourceDef
from skills.descriptive.sql import build_uv_pv_sql


def _src():
    return SourceDef(
        id="events", kind="trino", host="h", port=8443,
        catalog="bigdata_omega_common_iceberg", schema="axz_tiara", table="all_tiara_i",
        auth_ref="TIARA",
        column_map={
            "action_type": "action.type",
            "app_user_id": "user.app_user_id",
            "isuid": "user.isuid",
            "access_time": "try_cast(common.access_time AS timestamp)",
            "app_version": "env.app_version",
            "usage_duration": "try(cast(usage.duration as double))",
        },
        filters=["action.type IN ('Pageview','Event')"],
    )


def test_uv_pv_sql_core_pieces():
    sql = build_uv_pv_sql(_src(), ("2026-01-05", "2026-02-01"), "day", [], {})
    assert "bigdata_omega_common_iceberg.axz_tiara.all_tiara_i" in sql
    assert "date_trunc('day', try_cast(common.access_time AS timestamp)) AS period" in sql
    assert "COUNT(DISTINCT user.app_user_id) AS uv" in sql
    assert "COUNT(*) FILTER (WHERE action.type = 'Pageview') AS pv" in sql
    assert "action.type IN ('Pageview','Event')" in sql
    assert "2026-01-05 00:00:00" in sql and "2026-02-01 23:59:59" in sql
    assert "GROUP BY 1" in sql


def test_uv_pv_sql_breakdown_adds_dim_and_group():
    sql = build_uv_pv_sql(_src(), ("2026-01-05", "2026-02-01"), "week", ["app_version"], {})
    assert "date_trunc('week'," in sql
    assert "env.app_version AS app_version" in sql
    assert "GROUP BY 1, 2" in sql


def test_uv_pv_sql_filter_equality_is_escaped():
    sql = build_uv_pv_sql(_src(), ("2026-01-05", "2026-02-01"), "day", [], {"app_version": "10.5'x"})
    assert "env.app_version = '10.5''x'" in sql
