"""transition 큐브 SQL의 의미 검증 — 생성된 SQL을 DuckDB로 실제 실행한다.

문자열 테스트는 이 클래스의 버그를 못 잡는다. 실제로 이 파일을 만들면서 잡은 것:
`seq` 의 윈도 절이 한정되지 않아 `screens`/`kept` 양쪽의 `uuid` 가 충돌해
"Ambiguous reference" 로 죽는 상태였는데, 문자열 테스트 10개는 전부 통과했다.

`WITH ev AS (...)` 원천 CTE만 합성 프레임으로 갈아끼우고 **나머지 SQL은 프로덕션
문자열 그대로** 돌린다. 축 계산·state 표현식·귀속·윈도 함수가 전부 실행 경로에 든다.
"""
import duckdb
import pandas as pd
import pytest

from analytics.cube.sql import build_transition_cube_sql

DATE = "2026-07-27"
WINDOW = ["2026-07-26", "2026-07-27", "2026-07-28"]
SCREENS = ["top/홈탭_진입", "top/콘텐츠탭_진입"]

AXES = ("period", "service_type", "os", "gender", "age_band", "daypart", "app_version")


def _ev(rows) -> pd.DataFrame:
    """(ts, action_type, action_name) 또는 daypart 를 덧붙인 튜플을 ev CTE 출력 모양으로."""
    out = []
    for row in rows:
        ts, action_type, action_name = row[0], row[1], row[2]
        daypart = row[3] if len(row) > 3 else "주간"
        dur = row[4] if len(row) > 4 else 0.0
        out.append(
            {
                "uuid": "u1", "suid": "s1",
                "ts": pd.Timestamp(ts),
                "action_type": action_type,
                "action_name": action_name,
                "service_code": "top",
                "usage_duration": dur,
                "period": ts[:10],
                "service_type": "app",
                "os": "android",
                "gender": "M",
                "age_band": "30",
                "daypart": daypart,
                "app_version": "9.5.1",
            }
        )
    return pd.DataFrame(out)


def _run(ev: pd.DataFrame, screens: list[str] = SCREENS) -> pd.DataFrame:
    """프로덕션 SQL을 원천 CTE만 바꿔 DuckDB에서 실행한다."""
    sql = build_transition_cube_sql(
        events_table="ignored.events",
        demography_table="ignored.demography",
        date=DATE,
        window_dates=WINDOW,
        services=["top"],
        versions=["9.5.1"],
        screens=screens,
    )
    runnable = "WITH ev AS (SELECT * FROM ev_df),\n" + sql[sql.index("kept AS ("):]
    con = duckdb.connect()
    try:
        con.register("ev_df", ev)
        return con.execute(runnable).fetchdf()
    finally:
        con.close()


def _edges(df: pd.DataFrame) -> dict[tuple[str, str], int]:
    return {(r.from_state, r.to_state): int(r.cnt) for r in df.itertuples()}


def test_generated_sql_executes_at_all():
    # 한정되지 않은 윈도 절("Ambiguous reference")을 잡는 회귀 테스트.
    _run(_ev([(f"{DATE} 10:00", "Pageview", "홈탭_진입")]))


def test_emits_start_and_exit_around_a_screen_run():
    df = _run(
        _ev(
            [
                (f"{DATE} 10:00", "Pageview", "홈탭_진입"),
                (f"{DATE} 10:05", "Pageview", "콘텐츠탭_진입"),
            ]
        )
    )
    assert _edges(df) == {
        ("START", "top/홈탭_진입"): 1,
        ("top/홈탭_진입", "top/콘텐츠탭_진입"): 1,
        ("top/콘텐츠탭_진입", "EXIT"): 1,
    }


def test_screens_outside_the_dictionary_fold_into_other():
    df = _run(
        _ev(
            [
                (f"{DATE} 10:00", "Pageview", "홈탭_진입"),
                (f"{DATE} 10:05", "Pageview", "사전에_없는_화면"),
            ]
        )
    )
    assert ("top/홈탭_진입", "top/other") in _edges(df)


def test_session_starting_on_an_earlier_day_is_excluded():
    # 첫 이벤트가 D-1 이면 그 세션은 D-1 빌드의 몫이다. 여기서 또 세면 중복이다.
    df = _run(
        _ev(
            [
                ("2026-07-26 23:50", "Pageview", "홈탭_진입"),
                (f"{DATE} 00:10", "Pageview", "콘텐츠탭_진입"),
            ]
        )
    )
    assert df.empty


def test_session_without_any_pageview_contributes_no_edges():
    df = _run(_ev([(f"{DATE} 10:00", "Event", "버튼_클릭")]))
    assert df.empty


def test_axes_come_from_the_first_event_not_the_first_screen():
    """축은 첫 **이벤트** 기준이다. 첫 **화면** 기준이면 session 큐브와 어긋난다.

    `kept` 를 `screens` 에서 뽑던 계획 초안은 이 테스트에서 '주간' 을 냈다.
    """
    df = _run(
        _ev(
            [
                (f"{DATE} 05:50", "Event", "앱_실행", "새벽"),
                (f"{DATE} 06:10", "Pageview", "홈탭_진입", "주간"),
            ]
        )
    )
    assert df["daypart"].unique().tolist() == ["새벽"]


def test_attribution_day_comes_from_the_first_event_not_the_first_screen():
    # 첫 이벤트가 D-1 23:50(비-Pageview), 첫 화면이 D 00:10 인 세션은 D-1 의 몫이다.
    df = _run(
        _ev(
            [
                ("2026-07-26 23:50", "Event", "앱_실행"),
                (f"{DATE} 00:10", "Pageview", "홈탭_진입"),
            ]
        )
    )
    assert df.empty


def test_dur_sum_accumulates_the_departing_screen_duration():
    df = _run(
        _ev(
            [
                (f"{DATE} 10:00", "Pageview", "홈탭_진입", "주간", 12.0),
                (f"{DATE} 10:05", "Pageview", "콘텐츠탭_진입", "주간", 30.0),
            ]
        )
    )
    dur = {(r.from_state, r.to_state): r.dur_sum for r in df.itertuples()}
    assert dur[("START", "top/홈탭_진입")] == 0.0
    assert dur[("top/홈탭_진입", "top/콘텐츠탭_진입")] == 12.0
    assert dur[("top/콘텐츠탭_진입", "EXIT")] == 30.0


def test_every_core_axis_is_carried_through():
    df = _run(_ev([(f"{DATE} 10:00", "Pageview", "홈탭_진입")]))
    for axis in AXES:
        assert axis in df.columns


@pytest.mark.parametrize("screens", [[], SCREENS])
def test_empty_dictionary_still_produces_runnable_sql(screens):
    _run(_ev([(f"{DATE} 10:00", "Pageview", "홈탭_진입")]), screens=screens)
