"""세션 귀속 로직의 의미 검증 — Trino 없이 DuckDB로 실행한다.

Task 9의 자정 경계 버그 두 건(인접일 중복, 구멍 난 날짜 중복)은 문자열 테스트를 전부
통과했다. 이 파일은 그 클래스를 실행으로 잡는다.
"""
import duckdb
import pandas as pd
import pytest


def _count_for_build(events: pd.DataFrame, target: str, window: list[str]) -> int:
    """`target` 날짜 빌드가 채택하는 세션 수. Task 9 의 sess CTE 의미를 그대로 옮긴 것."""
    con = duckdb.connect()
    try:
        con.register("ev", events)
        rows = con.execute(
            """
            SELECT count(*) FROM (
              SELECT uuid, suid
              FROM ev
              WHERE date_id IN (SELECT unnest($window))
              GROUP BY uuid, suid
              HAVING date(min(ts)) = date($target)
            )
            """,
            {"window": window, "target": target},
        ).fetchall()
        return rows[0][0]
    finally:
        con.close()


def _window(day: str) -> list[str]:
    d = pd.Timestamp(day)
    return [(d - pd.Timedelta(days=1)).strftime("%Y-%m-%d"), day,
            (d + pd.Timedelta(days=1)).strftime("%Y-%m-%d")]


def _events(pairs):
    """(uuid, suid, 'YYYY-MM-DD HH:MM') 목록을 이벤트 프레임으로."""
    return pd.DataFrame(
        [
            {"uuid": u, "suid": s, "ts": pd.Timestamp(ts), "date_id": ts[:10]}
            for u, s, ts in pairs
        ]
    )


def _total_across_builds(events: pd.DataFrame, days: list[str]) -> int:
    return sum(_count_for_build(events, d, _window(d)) for d in days)


DAYS = ["2026-07-25", "2026-07-26", "2026-07-27", "2026-07-28", "2026-07-29"]


def test_session_within_one_day_counted_once():
    ev = _events([("u", "s", "2026-07-27 10:00"), ("u", "s", "2026-07-27 11:00")])
    assert _total_across_builds(ev, DAYS) == 1


def test_session_crossing_midnight_counted_once():
    # D-1 을 안 읽던 버전은 이걸 2로 셌다.
    ev = _events([("u", "s", "2026-07-26 23:50"), ("u", "s", "2026-07-27 00:10")])
    assert _total_across_builds(ev, DAYS) == 1


def test_session_attributed_to_its_first_event_day():
    ev = _events([("u", "s", "2026-07-26 23:50"), ("u", "s", "2026-07-27 00:10")])
    assert _count_for_build(ev, "2026-07-26", _window("2026-07-26")) == 1
    assert _count_for_build(ev, "2026-07-27", _window("2026-07-27")) == 0


def test_session_spanning_three_consecutive_days_counted_once():
    ev = _events([("u", "s", "2026-07-26 23:50"), ("u", "s", "2026-07-27 12:00"),
                  ("u", "s", "2026-07-28 00:10")])
    assert _total_across_builds(ev, DAYS) == 1


@pytest.mark.xfail(
    reason="알려진 잔여 한계: 중간 날짜에 이벤트가 없는 세션은 양쪽 빌드가 각자 세어 "
           "2회 집계된다. 실측 노출 890,062 세션 중 2건(0.0002%)이라 감시로 둔다 — "
           "quality 큐브의 session_span_exceeds_timeout 참조. 이 테스트가 통과로 바뀌면 "
           "구조적으로 닫힌 것이므로 스펙의 잔여 한계 항목을 갱신한다.",
    strict=True,
)
def test_session_skipping_the_middle_day_counted_once():
    ev = _events([("u", "s", "2026-07-26 10:00"), ("u", "s", "2026-07-28 10:00")])
    assert _total_across_builds(ev, DAYS) == 1


def test_two_distinct_sessions_counted_twice():
    ev = _events([("u", "s1", "2026-07-27 10:00"), ("u", "s2", "2026-07-27 20:00")])
    assert _total_across_builds(ev, DAYS) == 2
