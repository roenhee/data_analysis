"""transition 큐브 SQL의 의미 검증 — 생성된 SQL을 DuckDB로 실제 실행한다.

문자열 테스트는 이 클래스의 버그를 못 잡는다. 실제로 이 파일을 만들면서 잡은 것:
`seq` 의 윈도 절이 한정되지 않아 `screens`/`kept` 양쪽의 `uuid` 가 충돌해
"Ambiguous reference" 로 죽는 상태였는데, 문자열 테스트 10개는 전부 통과했다.

`WITH ev AS (...)` 원천 CTE만 합성 프레임으로 갈아끼우고 **나머지 SQL은 프로덕션
문자열 그대로** 돌린다. 축 계산·state 표현식·귀속·체류 귀속·윈도 함수가 전부 실행 경로에 든다.
"""
import duckdb
import pandas as pd
import pytest

from analytics.cube.sql import build_transition_cube_sql

DATE = "2026-07-27"
WINDOW = ["2026-07-26", "2026-07-27", "2026-07-28"]
SCREENS = ["top/홈탭_진입", "top/콘텐츠탭_진입"]

AXES = ("period", "service_type", "os", "gender", "age_band", "daypart", "app_version")


def _row(ts, action_type, action_kind, action_name, dwell=None, daypart="주간"):
    return {
        "uuid": "u1", "suid": "s1",
        "ts": pd.Timestamp(ts),
        "action_type": action_type,
        "action_kind": action_kind,
        "action_name": action_name,
        "service_code": "top",
        "usage_duration_ms": dwell,
        "period": ts[:10],
        "service_type": "app",
        "os": "android",
        "gender": "M",
        "age_band": "30",
        "daypart": daypart,
        "app_version": "9.5.1",
    }


def pv(ts, name="홈탭_진입", daypart="주간"):
    """화면 신호. 체류는 싣지 않는다 — 원천에서 Pageview 의 duration 은 항상 NULL."""
    return _row(ts, "Pageview", "ViewPage", name, None, daypart)


def usage(ts, dwell_sec, daypart="주간"):
    """체류 신호. 원천에서 체류는 이 행에만 실리고 **단위는 밀리초**다.

    테스트는 초로 쓰고 여기서 ms 로 바꿔 넣는다 — 그래야 SQL 의 ms→초 변환이
    실행 경로에 들어간다. 변환을 빼면 아래 기대값이 1000배로 어긋나 바로 잡힌다.
    """
    return _row(ts, "Usage", "UsagePage", "홈탭_진입", dwell_sec * 1000.0, daypart)


def other(ts, name="앱_실행", daypart="주간"):
    """화면도 체류도 아닌 이벤트. 귀속에는 쓰이되 상태는 만들지 않는다."""
    return _row(ts, "Event", "Click", name, None, daypart)


def _run(rows, screens=SCREENS, date=DATE, window=WINDOW) -> pd.DataFrame:
    """프로덕션 SQL을 원천 CTE만 바꿔 DuckDB에서 실행한다."""
    sql = build_transition_cube_sql(
        events_table="ignored.events",
        demography_table="ignored.demography",
        date=date,
        window_dates=window,
        services=["top"],
        versions=["9.5.1"],
        screens=screens,
    )
    runnable = "WITH ev AS (SELECT * FROM ev_df),\n" + sql[sql.index("kept AS ("):]
    con = duckdb.connect()
    try:
        con.register("ev_df", pd.DataFrame(rows))
        return con.execute(runnable).fetchdf()
    finally:
        con.close()


def _edges(df: pd.DataFrame) -> dict[tuple[str, str], int]:
    return {(r.from_state, r.to_state): int(r.cnt) for r in df.itertuples()}


def _dwell(df: pd.DataFrame) -> dict[tuple[str, str], tuple[float, int]]:
    return {
        (r.from_state, r.to_state): (float(r.dur_sum), int(r.dur_n))
        for r in df.itertuples()
    }


HOME, CONTENT = "top/홈탭_진입", "top/콘텐츠탭_진입"


# --- 전이 구조 ---------------------------------------------------------------

def test_generated_sql_executes_at_all():
    # 한정되지 않은 윈도 절("Ambiguous reference")을 잡는 회귀 테스트.
    _run([pv(f"{DATE} 10:00")])


def test_emits_start_and_exit_around_a_screen_run():
    df = _run([pv(f"{DATE} 10:00"), pv(f"{DATE} 10:05", "콘텐츠탭_진입")])
    assert _edges(df) == {
        ("START", HOME): 1,
        (HOME, CONTENT): 1,
        (CONTENT, "EXIT"): 1,
    }


def test_screens_outside_the_dictionary_fold_into_other():
    df = _run([pv(f"{DATE} 10:00"), pv(f"{DATE} 10:05", "사전에_없는_화면")])
    assert (HOME, "top/other") in _edges(df)


def test_session_starting_on_an_earlier_day_is_excluded():
    # 첫 이벤트가 D-1 이면 그 세션은 D-1 빌드의 몫이다. 여기서 또 세면 중복이다.
    df = _run([pv("2026-07-26 23:50"), pv(f"{DATE} 00:10", "콘텐츠탭_진입")])
    assert df.empty


def test_session_without_any_pageview_contributes_no_edges():
    assert _run([other(f"{DATE} 10:00")]).empty


def test_axes_come_from_the_first_event_not_the_first_screen():
    """축은 첫 **이벤트** 기준이다. 첫 **화면** 기준이면 session 큐브와 어긋난다."""
    df = _run([other(f"{DATE} 05:50", daypart="새벽"),
               pv(f"{DATE} 06:10", daypart="주간")])
    assert df["daypart"].unique().tolist() == ["새벽"]


def test_attribution_day_comes_from_the_first_event_not_the_first_screen():
    df = _run([other("2026-07-26 23:50"), pv(f"{DATE} 00:10")])
    assert df.empty


def test_every_core_axis_is_carried_through():
    df = _run([pv(f"{DATE} 10:00")])
    for axis in AXES:
        assert axis in df.columns


@pytest.mark.parametrize("screens", [[], SCREENS])
def test_empty_dictionary_still_produces_runnable_sql(screens):
    _run([pv(f"{DATE} 10:00")], screens=screens)


# --- 체류 귀속 ---------------------------------------------------------------

def test_dwell_comes_from_usage_rows_attached_to_the_preceding_screen():
    """체류는 Pageview 가 아니라 Usage 행에 실리고, 직전 화면 방문에 붙는다."""
    df = _run([
        pv(f"{DATE} 10:00"),
        usage(f"{DATE} 10:01", 12.0),
        pv(f"{DATE} 10:02", "콘텐츠탭_진입"),
        usage(f"{DATE} 10:03", 30.0),
    ])
    assert _dwell(df) == {
        ("START", HOME): (0.0, 0),
        (HOME, CONTENT): (12.0, 1),
        (CONTENT, "EXIT"): (30.0, 1),
    }


def test_multiple_usage_rows_in_one_visit_count_as_one_measured_visit():
    """`media` 는 Pageview 대비 UsagePage 가 107% 다 — 방문당 여러 건이 나온다.

    시간은 합치되 방문 수는 1이어야 `dur_sum / dur_n` 이 방문당 평균이 된다.
    """
    df = _run([
        pv(f"{DATE} 10:00"),
        usage(f"{DATE} 10:01", 5.0),
        usage(f"{DATE} 10:02", 7.0),
        pv(f"{DATE} 10:05", "콘텐츠탭_진입"),
    ])
    assert _dwell(df)[(HOME, CONTENT)] == (12.0, 1)


def test_visit_without_a_usage_row_is_excluded_from_dur_n():
    """체류가 없는 방문은 분모에서 빠진다 — 0 으로 세면 평균이 조용히 내려간다."""
    df = _run([
        pv(f"{DATE} 10:00"),
        pv(f"{DATE} 10:02", "콘텐츠탭_진입"),
        usage(f"{DATE} 10:03", 30.0),
    ])
    d = _dwell(df)
    assert d[(HOME, CONTENT)] == (0.0, 0)      # 커버리지 0/1
    assert d[(CONTENT, "EXIT")] == (30.0, 1)   # 커버리지 1/1


def test_adding_usage_rows_does_not_change_the_transition_counts():
    """`cnt` 는 화면 신호만으로 정해진다. 체류 신호가 상태를 만들면 안 된다."""
    without = _run([pv(f"{DATE} 10:00"), pv(f"{DATE} 10:05", "콘텐츠탭_진입")])
    with_dwell = _run([
        pv(f"{DATE} 10:00"),
        usage(f"{DATE} 10:01", 5.0),
        usage(f"{DATE} 10:02", 7.0),
        pv(f"{DATE} 10:05", "콘텐츠탭_진입"),
        usage(f"{DATE} 10:06", 3.0),
    ])
    assert _edges(without) == _edges(with_dwell)


def test_usage_before_the_first_screen_has_no_visit_to_attach_to():
    df = _run([usage(f"{DATE} 09:59", 99.0), pv(f"{DATE} 10:00")])
    assert _dwell(df)[(HOME, "EXIT")] == (0.0, 0)


def test_dwell_is_converted_from_milliseconds_to_seconds():
    """원천은 ms(최대값 10,799,978 = 정확히 3시간 상한이 증거). 큐브는 초로 낸다.

    세션 큐브의 `duration_sum` 이 `date_diff('second', ...)` 라 단위가 같아야 한다.
    """
    df = _run([pv(f"{DATE} 10:00"), usage(f"{DATE} 10:01", 90.0)])
    assert _dwell(df)[(HOME, "EXIT")] == (90.0, 1)


def test_dwell_at_the_same_timestamp_attaches_to_the_new_visit():
    """같은 ts 면 Pageview 가 먼저다 — 아니면 체류가 앞 방문으로 샌다."""
    df = _run([
        pv(f"{DATE} 10:00"),
        pv(f"{DATE} 10:05", "콘텐츠탭_진입"),
        usage(f"{DATE} 10:05", 20.0),
    ])
    d = _dwell(df)
    assert d[(HOME, CONTENT)] == (0.0, 0)
    assert d[(CONTENT, "EXIT")] == (20.0, 1)
