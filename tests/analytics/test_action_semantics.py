"""action 큐브 SQL의 의미 검증 — 생성된 SQL을 DuckDB로 실제 실행한다.

`WITH ev AS (...)` 원천 CTE만 합성 프레임으로 갈아끼우고 **나머지 SQL은 프로덕션 문자열
그대로** 돌린다. 축 계산·화면 표현식·귀속·`visit_idx` 윈도 함수·레이어 접기가 전부 실행
경로에 든다.

행 헬퍼는 `test_transition_semantics.py` 에서 **복제**했다 — 임포트하면 `tests/` 가
`sys.path` 에 올라 `tests/analytics/` 가 진짜 `analytics/` 를 가린다.
"""
import duckdb
import pandas as pd
import pytest

from analytics.cube.sql import build_action_cube_sql

DATE = "2026-07-27"
WINDOW = ["2026-07-26", "2026-07-27", "2026-07-28"]
SCREENS = ["top/홈탭_진입", "top/콘텐츠탭_진입"]
LAYER1 = ["home_main"]
LAYER2 = ["home_main>FEED"]


def _row(ts, action_type, action_kind, action_name, layer1=None, layer2=None,
         daypart="주간"):
    return {
        "uuid": "u1", "suid": "s1",
        "ts": pd.Timestamp(ts),
        "action_type": action_type,
        "action_kind": action_kind,
        "action_name": action_name,
        "service_code": "top",
        "page": "hometab",
        "layer1": layer1,
        "layer2": layer2,
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
    """화면 신호. Pageview 에는 슬롯 좌표가 없다."""
    return _row(ts, "Pageview", "ViewPage", name, None, None, daypart)


def click(ts, layer1="home_main", layer2="FEED", kind="ClickContent",
          name="클릭", daypart="주간"):
    """클릭 신호 — **슬롯 좌표가 있는 행**이 클릭의 정의다."""
    return _row(ts, "Event", kind, name, layer1, layer2, daypart)


def telemetry(ts, name="axzad_request", daypart="주간"):
    """광고 텔레메트리. 슬롯 좌표가 없어서 클릭이 아니다 — 실측 스트림의 34%다."""
    return _row(ts, "Event", None, name, None, None, daypart)


def usage(ts, dwell_sec=5.0, daypart="주간"):
    """체류 신호. 화면층이 이미 쓴다 — 행동으로 세면 분포가 오염된다."""
    row = _row(ts, "Usage", "UsagePage", "홈탭_진입", None, None, daypart)
    row["usage_duration_ms"] = dwell_sec * 1000.0
    return row


def _run(rows, screens=SCREENS, layer1=LAYER1, layer2=LAYER2, date=DATE,
         window=WINDOW) -> pd.DataFrame:
    """프로덕션 SQL을 원천 CTE만 바꿔 DuckDB에서 실행한다."""
    sql = build_action_cube_sql(
        events_table="ignored.events",
        demography_table="ignored.demography",
        date=date,
        window_dates=window,
        services=["top"],
        versions=["9.5.1"],
        screens=screens,
        layer1=layer1,
        layer2=layer2,
    )
    runnable = "WITH ev AS (SELECT * FROM ev_df),\n" + sql[sql.index("kept AS ("):]
    con = duckdb.connect()
    try:
        con.register("ev_df", pd.DataFrame(rows))
        return con.execute(runnable).fetchdf()
    finally:
        con.close()


def _by_screen(df: pd.DataFrame) -> dict[str, int]:
    return {r.screen: int(r.cnt) for r in df.itertuples()}


def test_a_click_is_attributed_to_the_screen_it_happened_on():
    got = _run([
        pv("2026-07-27 10:00:00", "홈탭_진입"),
        click("2026-07-27 10:00:05"),
        pv("2026-07-27 10:01:00", "콘텐츠탭_진입"),
        click("2026-07-27 10:01:05"),
    ])
    assert _by_screen(got) == {"top/홈탭_진입": 1, "top/콘텐츠탭_진입": 1}


def test_a_click_before_the_first_pageview_lands_on_start():
    """`visit_idx = 0`. 버리면 분포의 분모가 줄어든다."""
    got = _run([
        click("2026-07-27 09:59:00"),
        pv("2026-07-27 10:00:00", "홈탭_진입"),
        click("2026-07-27 10:00:05"),
    ])
    assert _by_screen(got) == {"START": 1, "top/홈탭_진입": 1}


def test_the_click_total_is_preserved_across_screens():
    """화면별 합 == 클릭 행 수. `START` 를 버리면 여기서 깨진다."""
    rows = [
        click("2026-07-27 09:59:00"),
        click("2026-07-27 09:59:30"),
        pv("2026-07-27 10:00:00", "홈탭_진입"),
        click("2026-07-27 10:00:05"),
    ]
    assert int(_run(rows)["cnt"].sum()) == 3


def test_pageview_rows_do_not_become_clicks():
    """화면 진입이 클릭으로 세어지면 분포가 화면 조회로 부푼다."""
    got = _run([pv("2026-07-27 10:00:00"), pv("2026-07-27 10:01:00")])
    assert got.empty


def test_a_row_without_a_slot_coordinate_is_not_a_click():
    """광고 텔레메트리·앱 생애주기가 여기서 빠진다 — 실측 스트림의 94.5%다."""
    got = _run([
        pv("2026-07-27 10:00:00", "홈탭_진입"),
        telemetry("2026-07-27 10:00:03"),
        telemetry("2026-07-27 10:00:04", "AppLaunch"),
        click("2026-07-27 10:00:05"),
    ])
    assert _by_screen(got) == {"top/홈탭_진입": 1}


def test_a_usage_row_is_not_a_click():
    got = _run([
        pv("2026-07-27 10:00:00", "홈탭_진입"),
        usage("2026-07-27 10:00:30"),
    ])
    assert got.empty


def test_the_screen_outside_the_dictionary_folds_to_service_other():
    got = _run([
        pv("2026-07-27 10:00:00", "사전에_없는_화면"),
        click("2026-07-27 10:00:05"),
    ])
    assert _by_screen(got) == {"top/other": 1}


def test_the_layer_outside_the_dictionary_folds_to_other():
    got = _run([
        pv("2026-07-27 10:00:00", "홈탭_진입"),
        click("2026-07-27 10:00:05", layer1="사전에_없는_레이어", layer2="X"),
    ])
    assert got["layer1"].tolist() == ["other"]
    assert got["layer2"].tolist() == ["other"]


def test_layer2_carries_its_layer1_prefix():
    """사전 값이 `layer1>layer2` 형태라 접두어가 없으면 사전과 안 맞는다."""
    got = _run([
        pv("2026-07-27 10:00:00", "홈탭_진입"),
        click("2026-07-27 10:00:05", layer1="home_main", layer2="FEED"),
    ])
    assert got["layer1"].tolist() == ["home_main"]
    assert got["layer2"].tolist() == ["home_main>FEED"]


def test_a_click_with_no_layer2_keeps_its_layer1_and_folds_layer2():
    """`layer1` 만 있는 클릭도 클릭이다 — 실측 search 는 layer2 가 0.64% 뿐이다."""
    got = _run([
        pv("2026-07-27 10:00:00", "홈탭_진입"),
        click("2026-07-27 10:00:05", layer1="home_main", layer2=None),
    ])
    assert got["layer1"].tolist() == ["home_main"]
    assert got["layer2"].tolist() == ["other"]


def test_a_missing_action_kind_becomes_none_not_null():
    """실측 클릭 집합의 절반이 kind 가 없다. NULL 이면 GROUP BY 에서 행이 갈린다."""
    got = _run([
        pv("2026-07-27 10:00:00", "홈탭_진입"),
        click("2026-07-27 10:00:05", kind=None),
    ])
    assert got["action_kind"].tolist() == ["(none)"]


def test_axes_come_from_the_first_event():
    """첫 이벤트가 클릭이어도 축은 그 행에서 온다 — 다른 큐브와 같은 귀속이어야 한다."""
    got = _run([
        click("2026-07-27 06:00:00", daypart="새벽"),
        pv("2026-07-27 10:00:00", "홈탭_진입", daypart="주간"),
        click("2026-07-27 10:00:05", daypart="주간"),
    ])
    assert set(got["daypart"]) == {"새벽"}


def test_a_session_starting_on_an_earlier_day_is_excluded():
    got = _run([
        pv("2026-07-26 23:50:00", "홈탭_진입"),
        click("2026-07-27 00:10:00"),
    ])
    assert got.empty


def test_a_second_pageview_at_the_same_timestamp_gets_its_own_visit():
    """`ROWS` 프레임이라 동시각 Pageview 둘이 서로 다른 방문 번호를 받는다.

    `RANGE` 로 바꾸면 둘이 한 방문이 되고, 뒤따르는 클릭이 어느 화면 것인지 어긋난다.
    """
    got = _run([
        pv("2026-07-27 10:00:00", "홈탭_진입"),
        pv("2026-07-27 10:00:00", "콘텐츠탭_진입"),
        click("2026-07-27 10:00:01"),
    ])
    # 두 번째 Pageview 가 마지막 방문이므로 클릭은 그쪽에 붙는다.
    assert _by_screen(got) == {"top/콘텐츠탭_진입": 1}


@pytest.mark.parametrize("click_first", [False, True])
def test_a_click_at_the_same_timestamp_as_a_pageview_belongs_to_that_visit(click_first):
    """`ORDER BY ts, is_screen DESC` 가 없으면 클릭이 앞 방문으로 새어 간다.

    **입력 행 순서를 뒤집어서도 확인한다.** `is_screen DESC` 없이도 엔진의 tie-break 가
    우연히 맞는 답을 낼 수 있어서, 한 순서로만 보면 정렬이 고정되지 않는다 — 실제로
    mutation check 에서 이 테스트가 결함을 놓쳤다.
    """
    same_ts = [
        pv("2026-07-27 10:01:00", "콘텐츠탭_진입"),
        click("2026-07-27 10:01:00"),
    ]
    if click_first:
        same_ts.reverse()
    got = _run([pv("2026-07-27 10:00:00", "홈탭_진입"), *same_ts])
    assert _by_screen(got) == {"top/콘텐츠탭_진입": 1}


def test_counts_add_up_when_a_screen_is_visited_twice():
    """같은 화면을 두 번 방문하면 클릭이 한 행으로 합쳐진다 — `cnt` 가 가산인 근거."""
    got = _run([
        pv("2026-07-27 10:00:00", "홈탭_진입"),
        click("2026-07-27 10:00:05"),
        pv("2026-07-27 10:02:00", "홈탭_진입"),
        click("2026-07-27 10:02:05"),
        click("2026-07-27 10:02:06"),
    ])
    assert _by_screen(got) == {"top/홈탭_진입": 3}
    assert len(got) == 1
