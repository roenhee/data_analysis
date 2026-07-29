import pandas as pd
import pytest

from analytics.metrics.descriptive import SESSION_AXES, engagement, uv_pv
from analytics.metrics.frame import NonAdditiveMeasureError


def _session_cube() -> pd.DataFrame:
    """전체 조합 2행 + os 접은 롤업 + 전체 롤업."""
    return pd.DataFrame([
        {"period": "2026-07-27", "service_type": "app", "os": "android",
         "gender": "M", "age_band": "30", "daypart": "주간", "app_version": "9.5.1",
         "sessions": 10, "uv": 8, "pv": 40, "events": 100, "duration_sum": 600},
        {"period": "2026-07-27", "service_type": "app", "os": "ios",
         "gender": "M", "age_band": "30", "daypart": "주간", "app_version": "9.5.1",
         "sessions": 5, "uv": 4, "pv": 15, "events": 50, "duration_sum": 300},
        {"period": "2026-07-27", "service_type": "app", "os": None,
         "gender": "M", "age_band": "30", "daypart": "주간", "app_version": "9.5.1",
         "sessions": 15, "uv": 11, "pv": 55, "events": 150, "duration_sum": 900},
        {"period": None, "service_type": None, "os": None, "gender": None,
         "age_band": None, "daypart": None, "app_version": None,
         "sessions": 15, "uv": 11, "pv": 55, "events": 150, "duration_sum": 900},
    ])


def test_uv_pv_reads_uv_from_the_rollup_row_not_by_summing():
    # android 8 + ios 4 = 12 이지만 실제 UV 는 11이다. 합산하면 조용히 부푼다.
    got = uv_pv(_session_cube(), folded=("os",))
    assert int(got.iloc[0]["uv"]) == 11
    assert int(got.iloc[0]["pv"]) == 55


def test_uv_pv_on_full_combination_rows_keeps_each_segment():
    got = uv_pv(_session_cube(), folded=())
    assert len(got) == 2
    assert set(got["os"]) == {"android", "ios"}


def test_uv_pv_drops_the_folded_axis_from_the_output():
    got = uv_pv(_session_cube(), folded=("os",))
    assert "os" not in got.columns
    assert "gender" in got.columns


def test_engagement_divides_by_sessions_and_users():
    got = engagement(_session_cube(), folded=("os",)).iloc[0]
    assert got["sessions_per_user"] == pytest.approx(15 / 11)
    assert got["pv_per_session"] == pytest.approx(55 / 15)
    assert got["seconds_per_session"] == pytest.approx(900 / 15)


def test_engagement_reports_the_session_span_definition_of_dwell():
    # 세션 큐브의 duration 은 세션 span(초)이고 커버리지 100% 다.
    got = engagement(_session_cube(), folded=("os",)).iloc[0]
    assert got["dwell_definition"] == "session_span_seconds"


def test_zero_sessions_yield_nan_not_a_division_error():
    empty = _session_cube().iloc[[0]].copy()
    empty.loc[:, ["sessions", "uv"]] = 0
    got = engagement(empty, folded=()).iloc[0]
    assert pd.isna(got["pv_per_session"])
    assert pd.isna(got["sessions_per_user"])


def test_uv_is_never_summed_even_if_asked_for_a_missing_rollup():
    # 요청한 롤업 조합이 큐브에 없으면 합산으로 때우지 않고 거부한다.
    cube = _session_cube()
    cube = cube[cube["os"].notna()]  # 롤업 행 제거
    with pytest.raises(NonAdditiveMeasureError, match="uv"):
        uv_pv(cube, folded=("os",))


def test_session_axes_match_the_cube():
    assert SESSION_AXES == (
        "period", "service_type", "os", "gender", "age_band", "daypart", "app_version",
    )
