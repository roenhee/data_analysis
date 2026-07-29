"""결과에 동봉할 커버리지 계산. 스펙이 "항상 동봉" 으로 지정한 항목들이다."""
import pandas as pd
import pytest

from analytics.metrics.coverage import (
    demography_coverage,
    dwell_coverage,
    screen_coverage,
)

SESSION_AXES = (
    "period", "service_type", "os", "gender", "age_band", "daypart", "app_version",
)


def _sessions(rows) -> pd.DataFrame:
    base = dict(period="2026-07-27", service_type="MA", os="android",
                daypart="주간", app_version="9.5.1")
    return pd.DataFrame(
        [{**base, "gender": g, "age_band": a, "sessions": s, "uv": s} for g, a, s in rows]
    )


def test_demography_coverage_is_the_share_with_a_known_band():
    # age_band='unknown' 은 성연령 테이블 매칭 실패 + 원천 센티널(0) 을 합친 버킷이다.
    got = demography_coverage(_sessions([("M", "30", 70), ("unknown", "unknown", 30)]))
    assert got["age_band_known"] == pytest.approx(0.7)
    assert got["gender_known"] == pytest.approx(0.7)


def test_demography_coverage_counts_sessions_not_rows():
    got = demography_coverage(_sessions([("M", "30", 90), ("M", "unknown", 10)]))
    assert got["age_band_known"] == pytest.approx(0.9)
    assert got["gender_known"] == pytest.approx(1.0)


def test_demography_coverage_of_an_empty_frame_is_nan_not_zero():
    # 0 으로 내면 "성연령이 하나도 안 붙었다"와 "셀 세션이 없다"가 구분되지 않는다.
    empty = _sessions([("M", "30", 1)]).iloc[0:0]
    got = demography_coverage(empty)
    assert pd.isna(got["age_band_known"])
    assert pd.isna(got["gender_known"])


def test_demography_coverage_ignores_rollup_rows():
    """롤업 행을 세면 같은 세션을 여러 번 센다 — 비율이 조용히 틀어진다."""
    cube = _sessions([("M", "30", 70), ("unknown", "unknown", 30)])
    rollup = cube.iloc[[0]].copy()
    rollup.loc[:, "os"] = None
    rollup.loc[:, "sessions"] = 100
    got = demography_coverage(pd.concat([cube, rollup], ignore_index=True))
    assert got["age_band_known"] == pytest.approx(0.7)


def test_dwell_coverage_is_measured_visits_over_visits():
    edges = pd.DataFrame([
        {"from_state": "top/A", "to_state": "EXIT", "cnt": 100, "dur_sum": 60.0, "dur_n": 57},
    ])
    assert dwell_coverage(edges) == pytest.approx(0.57)


def test_dwell_coverage_excludes_start_because_it_never_has_dwell():
    edges = pd.DataFrame([
        {"from_state": "START", "to_state": "top/A", "cnt": 100, "dur_sum": 0.0, "dur_n": 0},
        {"from_state": "top/A", "to_state": "EXIT", "cnt": 100, "dur_sum": 60.0, "dur_n": 57},
    ])
    # START 를 분모에 넣으면 커버리지가 절반으로 보인다.
    assert dwell_coverage(edges) == pytest.approx(0.57)


def test_screen_coverage_is_the_share_of_sessions_with_a_screen():
    q = pd.DataFrame([
        {"check_name": "session_no_screen", "violated": 22, "total": 100},
        {"check_name": "null_action_name", "violated": 10, "total": 100},
    ])
    assert screen_coverage(q) == pytest.approx(0.78)


def test_screen_coverage_needs_the_check_to_be_present():
    q = pd.DataFrame([{"check_name": "null_action_name", "violated": 10, "total": 100}])
    with pytest.raises(KeyError, match="session_no_screen"):
        screen_coverage(q)
