import pandas as pd
import pytest

from analytics.analyses.base import CubeSet, get_analysis

AXES = ("period", "service_type", "os", "gender", "age_band", "daypart", "app_version")

DEFAULT_SPEC = (("2026-07-27", 100, 60, 600.0), ("2026-07-28", 120, 70, 600.0))


def _day_rows(day: str, sessions: int, uv: int, seconds: float) -> list[dict]:
    """하루치 행 — 전체 조합 행 하나와 `(period)` 롤업 행 하나.

    큐브가 `GROUPING SETS` 로 만들어져 둘이 한 파일에 있다. 그냥 합산하면 두 번 센다.
    """
    base = dict(service_type="MA", os="android", gender="M", age_band="50",
                daypart="12~17", app_version="9.5.1")
    measures = {"sessions": sessions, "uv": uv, "pv": sessions * 8,
                "events": sessions * 30, "duration_sum": int(sessions * seconds)}
    return [
        {**base, "period": day, **measures},
        {**{k: None for k in AXES}, "period": day, **measures},
    ]


def _session_cube(spec=DEFAULT_SPEC) -> pd.DataFrame:
    rows = []
    for day, sessions, uv, seconds in spec:
        rows += _day_rows(day, sessions, uv, seconds)
    return pd.DataFrame(rows)


def _cubes(spec=DEFAULT_SPEC) -> CubeSet:
    cube = _session_cube(spec)
    days = sorted(set(cube["period"]))
    return CubeSet(session=cube, transition=None, quality=None,
                   state_dict_version="sd_abc", services=["top"],
                   requested_dates=days, present_dates=days)


def test_one_row_per_date():
    got = get_analysis("session_trend")(_cubes())
    assert len(got.frame) == 2


def test_uv_comes_from_the_rollup_row_not_a_sum():
    got = get_analysis("session_trend")(_cubes()).frame.set_index("period")
    assert int(got.loc["2026-07-27", "uv"]) == 60


def test_headline_carries_scalars_for_the_comparison_operator():
    got = get_analysis("session_trend")(_cubes())
    for k in ("sessions", "pv_per_session", "seconds_per_session"):
        assert k in got.headline


def test_day_kind_is_attached_when_a_calendar_is_given():
    got = get_analysis("session_trend")(_cubes(), holidays={"2026-07-27"})
    kinds = got.frame.set_index("period")["day_kind"]
    assert kinds["2026-07-27"] == "공휴일"


def test_without_a_calendar_no_day_kind_column_is_invented():
    # 공휴일을 모르면서 평일이라고 적으면 평균이 끌려간다(실측 584.2 vs 602.8초).
    assert "day_kind" not in get_analysis("session_trend")(_cubes()).frame.columns


def test_the_envelope_carries_coverage():
    got = get_analysis("session_trend")(_cubes())
    assert "gender_known" in got.envelope["coverage"]


def test_headline_seconds_are_volume_weighted_not_a_mean_of_days():
    """headline 은 기간 전체의 값이다 — 날짜별 값의 평균이 아니다.

    한 headline 안에서 `sessions` 는 합이고 `pv_per_session` 은 물량 가중인데
    `seconds_per_session` 만 날짜 평균이면 추정량이 섞인다. 그러면 `decompose` 의
    `between` 이 구성 변화가 아니라 추정량 차이를 담는다.

    여기선 100세션 600초 / 900세션 100초라 물량 가중은 150초, 날짜 평균은 350초다.
    """
    skewed = _cubes((("2026-07-27", 100, 60, 600.0), ("2026-07-28", 900, 500, 100.0)))
    got = get_analysis("session_trend")(skewed)
    assert got.headline["seconds_per_session"] == pytest.approx(150.0)


def test_the_frame_carries_the_duration_the_headline_is_built_from():
    """비율만 내면 소비자가 headline 을 검산할 수 없다."""
    got = get_analysis("session_trend")(_cubes()).frame.set_index("period")
    assert int(got.loc["2026-07-27", "duration_sum"]) == 60000


def test_a_segment_slice_still_gives_the_additive_measures():
    """버전으로 자르면 `(period)` 롤업 행이 사라진다. 가산 측정값은 그대로 낼 수 있다."""
    from tests.analytics.analyses.test_compare_on_session_cubes import _cubes

    sliced = _cubes().filter(app_version="9.5.1")
    got = get_analysis("session_trend")(sliced).frame.set_index("period")
    # 전체 조합 행만 합한다: gender M 100 + F 100 = 200 (gender 접은 200 을 더하면 400)
    assert int(got.loc["2026-07-27", "sessions"]) == 200
    assert int(got.loc["2026-07-27", "duration_sum"]) == 132_000
    assert got.loc["2026-07-27", "seconds_per_session"] == pytest.approx(660.0)


def test_uv_is_nan_on_a_slice_rather_than_a_sum():
    """`uv` 를 합하면 실측 1.71배로 부푼다. 모르는 것은 NaN 이다."""
    from tests.analytics.analyses.test_compare_on_session_cubes import _cubes

    sliced = _cubes().filter(app_version="9.5.1")
    got = get_analysis("session_trend")(sliced)
    assert got.frame["uv"].isna().all()
    assert pd.isna(got.frame["sessions_per_user"].iloc[0])


def test_the_envelope_says_uv_could_not_be_read_for_the_slice():
    from tests.analytics.analyses.test_compare_on_session_cubes import _cubes

    sliced = _cubes().filter(app_version="9.5.1")
    got = get_analysis("session_trend")(sliced)
    assert [w["check_name"] for w in got.envelope["warnings"]] == [
        "uv_unavailable_for_this_slice"
    ]


def test_an_unsliced_cube_still_reads_uv_from_the_rollup_row():
    """fallback 이 생겼다고 자르지 않은 경우까지 합산으로 가면 안 된다."""
    got = get_analysis("session_trend")(_cubes()).frame.set_index("period")
    assert int(got.loc["2026-07-27", "uv"]) == 60
    assert not get_analysis("session_trend")(_cubes()).envelope["warnings"]
