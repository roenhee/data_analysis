"""quality 큐브 SQL의 의미 검증 — 생성된 SQL을 DuckDB로 실제 실행한다.

핵심은 `session_span_exceeds_timeout` 이다. 이 검사는 스펙이 자정 경계 중복집계의
**상시 감시 장치**로 지정한 것인데, 단일 파티션으로 재면 자정을 넘긴 세션의 span 이
절단돼 감시 대상인 바로 그 세션을 못 본다. 문자열 테스트로는 드러나지 않는다.

`WITH ev AS (...)` 원천 CTE만 합성 프레임으로 갈아끼우고 나머지는 프로덕션 문자열
그대로 돌린다. 다만 `ev` 안의 `nullif(trim(...))` 정규화는 실행 경로에서 빠지므로,
합성 프레임에는 **정규화된 뒤의 값**(빈 문자열이 아니라 `None`)을 넣는다.
"""
import duckdb
import pandas as pd

from analytics.cube.sql import build_quality_cube_sql

SERVICES = ["top"]


def _ev(rows) -> pd.DataFrame:
    """(ts, action_type, action_kind, action_name, page) 목록을 ev CTE 출력 모양으로."""
    return pd.DataFrame(
        [
            {
                "period": r[0][:10],
                "service_code": "top",
                "app_version": "9.5.1",
                "uuid": r[5] if len(r) > 5 else "u1",
                "suid": r[6] if len(r) > 6 else "s1",
                "action_type": r[1],
                "action_kind": r[2],
                "action_name": r[3],
                "page": r[4],
                "ts": pd.Timestamp(r[0]),
            }
            for r in rows
        ]
    )


def _run(ev: pd.DataFrame, date: str, window: list[str]) -> pd.DataFrame:
    sql = build_quality_cube_sql(
        events_table="ignored.events",
        date=date,
        window_dates=window,
        services=SERVICES,
    )
    runnable = "WITH ev AS (SELECT * FROM ev_df),\n" + sql[sql.index("day AS ("):]
    con = duckdb.connect()
    try:
        con.register("ev_df", ev)
        return con.execute(runnable).fetchdf()
    finally:
        con.close()


def _check(df: pd.DataFrame, name: str) -> tuple[int, int]:
    row = df[df["check_name"] == name]
    assert len(row) == 1, f"{name}: {len(row)} 행"
    return int(row.iloc[0]["violated"]), int(row.iloc[0]["total"])


WINDOW_26 = ["2026-07-25", "2026-07-26", "2026-07-27"]
WINDOW_27 = ["2026-07-26", "2026-07-27", "2026-07-28"]


def test_generated_sql_executes_at_all():
    ev = _ev([("2026-07-27 10:00", "Pageview", "ViewPage", "홈탭_진입", "home")])
    assert not _run(ev, "2026-07-27", WINDOW_27).empty


def test_span_watchdog_sees_a_session_that_crosses_midnight():
    """6시간 1분짜리 자정 횡단 세션은 **첫 이벤트 날짜에서 정확히 한 번** 잡혀야 한다.

    단일 파티션만 읽던 계획 초안은 양쪽 빌드 모두 0을 냈다 — 감시 장치가 눈이 먼 상태.
    """
    ev = _ev(
        [
            ("2026-07-26 22:00", "Pageview", "ViewPage", "홈탭_진입", "home"),
            ("2026-07-27 04:01", "Pageview", "ViewPage", "홈탭_진입", "home"),
        ]
    )
    violated_26, total_26 = _check(
        _run(ev, "2026-07-26", WINDOW_26), "session_span_exceeds_timeout"
    )
    assert (violated_26, total_26) == (1, 1)

    # D 빌드는 같은 세션을 다시 세지 않는다 (첫 이벤트가 D-1 이므로).
    # 행 단위 검사는 D 파티션의 04:01 행을 계속 재므로 프레임 자체는 비지 않는다 —
    # 사라져야 하는 것은 세션 단위 검사뿐이다.
    on_27 = _run(ev, "2026-07-27", WINDOW_27)
    assert on_27[on_27["check_name"] == "session_span_exceeds_timeout"].empty
    assert on_27[on_27["check_name"] == "session_no_screen"].empty
    assert not on_27[on_27["check_name"] == "null_action_name"].empty


def test_row_checks_count_only_the_target_partition():
    # 창에 3일치가 들어와도 행 단위 분모는 대상 날짜의 행 수여야 한다.
    ev = _ev(
        [
            ("2026-07-26 10:00", "Event", "Click", None, "home"),
            ("2026-07-26 11:00", "Event", "Click", None, "home"),
            ("2026-07-27 10:00", "Event", "Click", None, "home"),
        ]
    )
    violated, total = _check(_run(ev, "2026-07-27", WINDOW_27), "null_action_name")
    assert total == 1
    assert violated == 1


def test_session_no_screen_counts_sessions_without_any_pageview():
    ev = _ev(
        [
            ("2026-07-27 10:00", "Event", "Click", "버튼", "home", "u1", "s1"),
            ("2026-07-27 10:00", "Pageview", "ViewPage", "홈탭_진입", "home", "u2", "s2"),
        ]
    )
    violated, total = _check(_run(ev, "2026-07-27", WINDOW_27), "session_no_screen")
    assert (violated, total) == (1, 2)


def test_page_name_ambiguous_flags_a_name_serving_two_pages():
    ev = _ev(
        [
            ("2026-07-27 10:00", "Pageview", "ViewPage", "홈탭_진입", "home"),
            ("2026-07-27 10:05", "Pageview", "ViewPage", "홈탭_진입", "other_page"),
            ("2026-07-27 10:10", "Pageview", "ViewPage", "콘텐츠탭_진입", "content"),
        ]
    )
    violated, total = _check(_run(ev, "2026-07-27", WINDOW_27), "page_name_ambiguous")
    assert (violated, total) == (1, 2)


def test_pageview_null_kind_is_counted_against_all_rows():
    ev = _ev(
        [
            ("2026-07-27 10:00", "Pageview", None, "홈탭_진입", "home"),
            ("2026-07-27 10:05", "Event", None, "버튼", "home"),
        ]
    )
    violated, total = _check(_run(ev, "2026-07-27", WINDOW_27), "pageview_null_kind")
    assert (violated, total) == (1, 2)


def test_screen_other_ratio_is_measured_against_pageview_rows_only():
    ev = _ev(
        [
            ("2026-07-27 10:00", "Pageview", "ViewPage", None, "home"),
            ("2026-07-27 10:05", "Pageview", "ViewPage", "홈탭_진입", "home"),
            ("2026-07-27 10:10", "Event", "Click", None, "home"),
        ]
    )
    violated, total = _check(_run(ev, "2026-07-27", WINDOW_27), "screen_other_ratio")
    assert (violated, total) == (1, 2)


def test_sessions_are_attributed_to_the_first_event_day():
    # 첫 이벤트가 D 인 세션만 세션 검사에 든다.
    ev = _ev(
        [
            ("2026-07-26 23:50", "Pageview", "ViewPage", "홈탭_진입", "home", "u1", "s1"),
            ("2026-07-27 00:10", "Pageview", "ViewPage", "홈탭_진입", "home", "u1", "s1"),
            ("2026-07-27 09:00", "Pageview", "ViewPage", "홈탭_진입", "home", "u2", "s2"),
        ]
    )
    _, total = _check(_run(ev, "2026-07-27", WINDOW_27), "session_no_screen")
    assert total == 1
