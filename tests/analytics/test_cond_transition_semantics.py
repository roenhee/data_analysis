"""cond_transition 큐브 SQL의 의미 검증 — 생성된 SQL을 DuckDB로 실제 실행한다.

**이 단계에서 가장 틀리기 쉬운 자리다.** `cnt` 는 전이 수가 아니고, 클릭 없는 전이와
종류 없는 클릭이 다른 라벨을 받아야 한다.

행 헬퍼는 `test_action_semantics.py` 에서 복제했다 — 임포트하면 `tests/` 가 `sys.path` 에
올라 `tests/analytics/` 가 진짜 `analytics/` 를 가린다.
"""
import duckdb
import pandas as pd

from analytics.cube.sql import build_cond_transition_cube_sql

DATE = "2026-07-27"
WINDOW = ["2026-07-26", "2026-07-27", "2026-07-28"]
SCREENS = ["top/홈탭_진입", "top/콘텐츠탭_진입"]


def _row(ts, action_type, action_kind, action_name, layer1=None, daypart="주간"):
    return {
        "uuid": "u1", "suid": "s1",
        "ts": pd.Timestamp(ts),
        "action_type": action_type,
        "action_kind": action_kind,
        "action_name": action_name,
        "service_code": "top",
        "page": "hometab",
        "layer1": layer1,
        "layer2": None,
        "usage_duration_ms": None,
        "period": ts[:10],
        "service_type": "app",
        "os": "android",
        "gender": "M",
        "age_band": "30",
        "daypart": daypart,
        "app_version": "9.5.1",
    }


def pv(ts, name="홈탭_진입", daypart="주간"):
    return _row(ts, "Pageview", "ViewPage", name, None, daypart)


def click(ts, kind="ClickContent", layer1="home_main", daypart="주간"):
    """슬롯 좌표가 있는 행 = 클릭."""
    return _row(ts, "Event", kind, "클릭", layer1, daypart)


def telemetry(ts, name="axzad_request", daypart="주간"):
    """슬롯 좌표가 없어서 클릭이 아니다."""
    return _row(ts, "Event", None, name, None, daypart)


def _run(rows, screens=SCREENS, date=DATE, window=WINDOW) -> pd.DataFrame:
    sql = build_cond_transition_cube_sql(
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


def _triples(df: pd.DataFrame) -> dict[tuple[str, str, str], int]:
    return {
        (r.from_state, r.action_kind, r.to_state): int(r.cnt)
        for r in df.itertuples()
    }


def test_a_click_is_attributed_to_the_visit_it_happened_in():
    """홈탭 방문 중 누른 클릭은 홈탭 -> 다음화면 전이에 붙는다."""
    got = _triples(_run([
        pv("2026-07-27 10:00:00", "홈탭_진입"),
        click("2026-07-27 10:00:05"),
        pv("2026-07-27 10:01:00", "콘텐츠탭_진입"),
    ]))
    assert got[("top/홈탭_진입", "ClickContent", "top/콘텐츠탭_진입")] == 1


def test_a_transition_with_no_click_is_labelled_no_click():
    """행동 없이 넘어간 전이도 세어야 한다. 빠뜨리면 분모가 줄어든다."""
    got = _triples(_run([
        pv("2026-07-27 10:00:00", "홈탭_진입"),
        pv("2026-07-27 10:01:00", "콘텐츠탭_진입"),
    ]))
    assert got[("top/홈탭_진입", "(no_click)", "top/콘텐츠탭_진입")] == 1
    assert got[("top/콘텐츠탭_진입", "(no_click)", "EXIT")] == 1


def test_a_click_with_no_kind_is_not_confused_with_a_visit_with_no_click():
    """**둘은 다른 것이다.** 실측 클릭 집합의 절반이 `action.kind` 가 없다.

    같은 라벨에 넣으면 "행동 없이 넘어갔다" 와 "무슨 행동인지 모른다" 가 뭉개진다.
    """
    got = _triples(_run([
        pv("2026-07-27 10:00:00", "홈탭_진입"),
        click("2026-07-27 10:00:05", kind=None),      # 클릭인데 kind 없음
        pv("2026-07-27 10:01:00", "콘텐츠탭_진입"),   # 이 방문은 클릭 없음
    ]))
    assert got[("top/홈탭_진입", "(none)", "top/콘텐츠탭_진입")] == 1
    assert got[("top/콘텐츠탭_진입", "(no_click)", "EXIT")] == 1
    assert ("top/홈탭_진입", "(no_click)", "top/콘텐츠탭_진입") not in got


def test_a_visit_with_several_clicks_becomes_several_rows():
    """**`cnt` 는 전이 수가 아니다.** 클릭이 k개면 그 전이가 k행으로 나온다."""
    got = _triples(_run([
        pv("2026-07-27 10:00:00", "홈탭_진입"),
        click("2026-07-27 10:00:05", kind="ClickContent"),
        click("2026-07-27 10:00:06", kind="ClickContent"),
        click("2026-07-27 10:00:07", kind="Share"),
        pv("2026-07-27 10:01:00", "콘텐츠탭_진입"),
    ]))
    assert got[("top/홈탭_진입", "ClickContent", "top/콘텐츠탭_진입")] == 2
    assert got[("top/홈탭_진입", "Share", "top/콘텐츠탭_진입")] == 1
    # 클릭이 있으므로 `(no_click)` 행은 없다
    assert ("top/홈탭_진입", "(no_click)", "top/콘텐츠탭_진입") not in got


def test_the_total_is_never_smaller_than_the_transition_count():
    """엣지 3개 + 클릭이 그중 하나에 3개 = 합 5. **`START` 엣지를 빼고 세지 말 것.**

    엣지는 `START->홈탭`, `홈탭->콘텐츠탭`, `콘텐츠탭->EXIT` 셋이다(전이 큐브와 같은 모양).
    클릭 3개가 두 번째에 붙어 그 엣지가 3행이 되고, 나머지 둘은 `(no_click)` 1행씩이다.
    처음 이 테스트를 쓸 때 `START` 를 빼고 4를 기대했다 — SQL 이 아니라 기대값이 틀렸다.

    고정하는 성질: **합은 엣지 수보다 작을 수 없다**(클릭 없는 엣지도 1행이므로).
    """
    got = _run([
        pv("2026-07-27 10:00:00", "홈탭_진입"),
        click("2026-07-27 10:00:05"),
        click("2026-07-27 10:00:06"),
        click("2026-07-27 10:00:07"),
        pv("2026-07-27 10:01:00", "콘텐츠탭_진입"),
    ])
    edges = 3
    assert int(got["cnt"].sum()) == 5
    assert int(got["cnt"].sum()) >= edges


def test_a_click_before_the_first_screen_lands_on_the_start_edge():
    """붙을 곳이 없으면 조용히 사라진다. 전이 큐브가 이미 `START` 엣지를 갖고 있다."""
    got = _triples(_run([
        click("2026-07-27 09:59:00"),
        pv("2026-07-27 10:00:00", "홈탭_진입"),
    ]))
    assert got[("START", "ClickContent", "top/홈탭_진입")] == 1
    assert ("START", "(no_click)", "top/홈탭_진입") not in got


def test_the_start_edge_gets_no_click_when_nothing_precedes_the_first_screen():
    got = _triples(_run([
        pv("2026-07-27 10:00:00", "홈탭_진입"),
    ]))
    assert got[("START", "(no_click)", "top/홈탭_진입")] == 1
    assert got[("top/홈탭_진입", "(no_click)", "EXIT")] == 1


def test_a_row_without_a_slot_coordinate_is_not_a_click():
    """광고 텔레메트리가 전이에 붙으면 "행동이 결정한다" 는 결론이 오염된다."""
    got = _triples(_run([
        pv("2026-07-27 10:00:00", "홈탭_진입"),
        telemetry("2026-07-27 10:00:05"),
        pv("2026-07-27 10:01:00", "콘텐츠탭_진입"),
    ]))
    assert got[("top/홈탭_진입", "(no_click)", "top/콘텐츠탭_진입")] == 1


def test_the_last_visit_transitions_to_exit():
    got = _triples(_run([
        pv("2026-07-27 10:00:00", "홈탭_진입"),
        click("2026-07-27 10:00:05"),
    ]))
    assert got[("top/홈탭_진입", "ClickContent", "EXIT")] == 1


def test_only_the_four_reduced_axes_are_emitted():
    got = _run([pv("2026-07-27 10:00:00", "홈탭_진입")])
    assert set(got.columns) == {
        "period", "service_type", "os", "app_version",
        "from_state", "action_kind", "to_state", "cnt",
    }


def test_axes_come_from_the_first_event():
    got = _run([
        click("2026-07-27 06:00:00", daypart="새벽"),
        pv("2026-07-27 10:00:00", "홈탭_진입", daypart="주간"),
    ])
    # daypart 는 축이 아니지만 귀속은 첫 이벤트라 period 가 그 날이어야 한다.
    assert set(got["period"]) == {"2026-07-27"}


def test_a_session_starting_on_an_earlier_day_is_excluded():
    got = _run([
        pv("2026-07-26 23:50:00", "홈탭_진입"),
        click("2026-07-27 00:10:00"),
        pv("2026-07-27 00:20:00", "콘텐츠탭_진입"),
    ])
    assert got.empty


def test_the_screen_outside_the_dictionary_folds_to_service_other():
    got = _triples(_run([
        pv("2026-07-27 10:00:00", "사전에_없는_화면"),
        click("2026-07-27 10:00:05"),
        pv("2026-07-27 10:01:00", "홈탭_진입"),
    ]))
    assert got[("top/other", "ClickContent", "top/홈탭_진입")] == 1
