import pandas as pd
import pytest

from data_layer.results import read_result
from data_layer.sources import SourceDef
from skills.descriptive.run import run_analysis


def _src():
    return SourceDef(
        id="events", kind="trino", host="h", port=8443,
        catalog="c", schema="s", table="t", auth_ref="TIARA",
        column_map={
            "action_type": "action.type",
            "app_user_id": "user.app_user_id",
            "isuid": "user.isuid",
            "access_time": "try_cast(common.access_time AS timestamp)",
            "app_version": "env.app_version",
            "usage_duration": "try(cast(usage.duration as double))",
        },
    )


def _fake_uv_pv(config, source, sql):
    return pd.DataFrame(
        {"period": ["2026-01-05", "2026-01-06"], "uv": [10, 12], "pv": [30, 40]}
    )


def test_run_uv_pv_publishes_contract_result(config):
    rid = run_analysis(
        config, _src(), "uv_pv_by_period",
        params={"window": ["2026-01-05", "2026-01-06"], "grain": "day"},
        run_id="r1", config_version="cfg1", aggregate_fetcher=_fake_uv_pv,
    )
    df, env = read_result(config, rid)
    assert list(df.columns) == ["period", "uv", "pv"]
    assert env["skill"] == "descriptive"
    assert env["analysis_type"] == "uv_pv_by_period"
    assert env["viz"]["chart_type"] == "line"
    assert "전수집계(비샘플)" in env["caveats"]


def test_run_rejects_unknown_analysis_type(config):
    calls = {"n": 0}

    def counting(config, source, sql):
        calls["n"] += 1
        return _fake_uv_pv(config, source, sql)

    with pytest.raises(ValueError, match="unknown analysis_type"):
        run_analysis(
            config, _src(), "nope", params={"window": ["a", "b"]},
            run_id="r", config_version="c", aggregate_fetcher=counting,
        )
    assert calls["n"] == 0


def test_run_rejects_bad_grain(config):
    with pytest.raises(ValueError, match="grain"):
        run_analysis(
            config, _src(), "uv_pv_by_period",
            params={"window": ["a", "b"], "grain": "fortnight"},
            run_id="r", config_version="c", aggregate_fetcher=_fake_uv_pv,
        )


def test_run_rejects_bad_breakdown(config):
    with pytest.raises(ValueError, match="whitelist"):
        run_analysis(
            config, _src(), "uv_pv_by_period",
            params={"window": ["a", "b"], "breakdown": ["evil_col"]},
            run_id="r", config_version="c", aggregate_fetcher=_fake_uv_pv,
        )


def _fake_session(config, source, sql):
    return pd.DataFrame(
        {"period": ["2026-01-05"], "sessions": [8], "uv": [4], "total_duration": [200.0]}
    )


def test_run_session_engagement_derives_per_user(config):
    rid = run_analysis(
        config, _src(), "session_engagement_by_period",
        params={"window": ["2026-01-05", "2026-01-05"], "grain": "day"},
        run_id="r1", config_version="cfg1", aggregate_fetcher=_fake_session,
    )
    df, env = read_result(config, rid)
    assert "uv" not in df.columns
    row = df.iloc[0]
    assert row["sessions_per_user"] == 2.0
    assert row["duration_per_user"] == 50.0
    assert row["avg_duration_per_session"] == 25.0


def test_run_session_engagement_handles_zero_uv(config):
    def fake(config, source, sql):
        return pd.DataFrame(
            {"period": ["2026-01-05"], "sessions": [0], "uv": [0], "total_duration": [0.0]}
        )

    rid = run_analysis(
        config, _src(), "session_engagement_by_period",
        params={"window": ["2026-01-05", "2026-01-05"]},
        run_id="r1", config_version="cfg1", aggregate_fetcher=fake,
    )
    df, _ = read_result(config, rid)
    assert pd.isna(df.iloc[0]["sessions_per_user"])
