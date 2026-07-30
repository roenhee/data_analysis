"""path 큐브 SQL의 의미 검증 — 생성된 SQL을 DuckDB로 실제 실행한다.

**배열을 안 쓴 이유가 여기 있다.** Trino `slice(arr, start, 길이)` 와 DuckDB
`list_slice(arr, begin, 끝인덱스)` 는 세 번째 인자의 뜻이 달라서, 배열로 만들면 이 파일이
프로덕션과 **다른 길이**의 n-gram 을 검증하고 그 오차는 예외를 안 던진다. `lead()` 와 `||`
는 두 방언에서 같으므로 그대로 돌린다.
"""
import duckdb
import pandas as pd

from analytics.cube.sql import OTHER_PATH, build_path_cube_sql

DATE = "2026-07-27"
WINDOW = ["2026-07-26", "2026-07-27", "2026-07-28"]
SCREENS = ["top/a", "top/b", "top/c", "top/d", "top/e", "top/f"]


def pv(ts, name, daypart="주간"):
    return {
        "uuid": "u1", "suid": "s1",
        "ts": pd.Timestamp(ts),
        "action_type": "Pageview",
        "action_kind": "ViewPage",
        "action_name": name,
        "service_code": "top",
        "page": "p",
        "layer1": None,
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


def _walk(names, start="2026-07-27 10:00:00", uuid="u1", suid="s1"):
    """한 세션이 `names` 순서로 화면을 밟는다."""
    base = pd.Timestamp(start)
    rows = []
    for i, name in enumerate(names):
        row = pv(str(base + pd.Timedelta(minutes=i))[:19], name)
        row["uuid"], row["suid"] = uuid, suid
        rows.append(row)
    return rows


def _run(rows, screens=SCREENS, top_n=200, date=DATE, window=WINDOW) -> pd.DataFrame:
    sql = build_path_cube_sql(
        events_table="ignored.events",
        demography_table="ignored.demography",
        date=date,
        window_dates=window,
        services=["top"],
        versions=["9.5.1"],
        screens=screens,
        top_n=top_n,
    )
    runnable = "WITH ev AS (SELECT * FROM ev_df),\n" + sql[sql.index("kept AS ("):]
    con = duckdb.connect()
    try:
        con.register("ev_df", pd.DataFrame(rows))
        return con.execute(runnable).fetchdf()
    finally:
        con.close()


def _paths(df: pd.DataFrame, n: int) -> dict[str, int]:
    rows = df[df["n"] == n]
    return {r.path: int(r.cnt) for r in rows.itertuples()}


def test_a_session_shorter_than_n_produces_no_ngram():
    """화면 2개면 n=3 경로가 없다. `lead` 가 NULL 을 주고 `||` 가 전파한다."""
    got = _run(_walk(["a", "b"]))
    assert _paths(got, 3) == {}
    assert _paths(got, 4) == {}
    assert _paths(got, 5) == {}


def test_a_session_of_exactly_n_produces_one_ngram():
    got = _run(_walk(["a", "b", "c"]))
    assert _paths(got, 3) == {"top/a>top/b>top/c": 1}
    assert _paths(got, 4) == {}


def test_a_session_of_n_plus_one_produces_two_overlapping_ngrams():
    """겹치는 창이다 — a>b>c 와 b>c>d 를 둘 다 낸다."""
    got = _run(_walk(["a", "b", "c", "d"]))
    assert _paths(got, 3) == {"top/a>top/b>top/c": 1, "top/b>top/c>top/d": 1}
    assert _paths(got, 4) == {"top/a>top/b>top/c>top/d": 1}
    assert _paths(got, 5) == {}


def test_the_ngram_length_is_exactly_n():
    """방언 차이로 길이가 어긋나면 여기서 잡힌다 — `>` 개수가 n-1 이어야 한다."""
    got = _run(_walk(["a", "b", "c", "d", "e", "f"]))
    for n in (3, 4, 5):
        for path in _paths(got, n):
            assert path.count(">") == n - 1, (n, path)


def test_repeated_walks_add_up():
    """같은 경로를 두 세션이 밟으면 `cnt` 가 2다."""
    rows = _walk(["a", "b", "c"]) + _walk(
        ["a", "b", "c"], start="2026-07-27 12:00:00", uuid="u2", suid="s2"
    )
    assert _paths(_run(rows), 3) == {"top/a>top/b>top/c": 2}


def test_the_other_row_preserves_the_total():
    """상위 N + `(other)` 의 합 == 컷 이전 전체. 깨지면 경로 분포의 분모가 조용히 틀린다."""
    # n=3 경로 넷: a>b>c(2회), b>c>d, c>d>e, d>e>f
    rows = _walk(["a", "b", "c", "d", "e", "f"]) + _walk(
        ["a", "b", "c"], start="2026-07-27 12:00:00", uuid="u2", suid="s2"
    )
    uncut = _run(rows, top_n=200)
    cut = _run(rows, top_n=2)
    assert OTHER_PATH not in _paths(uncut, 3)
    assert OTHER_PATH in _paths(cut, 3)
    assert sum(_paths(cut, 3).values()) == sum(_paths(uncut, 3).values())


def test_distinct_dropped_counts_paths_not_events():
    """커버리지 하나로는 "200개가 꼬리 전부" 와 "20만 개를 잘랐" 가 구분되지 않는다.

    **잘린 경로 중 하나가 2회여야 종수와 건수가 갈린다.** 전부 1회인 픽스처로는
    `count(*)` 와 `sum(cnt)` 가 같은 값이라 가중을 검증할 수 없다 — mutation check 가
    그렇게 결함을 놓쳤다.

    n=3 경로: a>b>c 2회, c>d>e 2회, b>c>d 1회, d>e>f 1회. top 1 을 남기면 잘린 종수는 3,
    건수는 4다.
    """
    rows = (
        _walk(["a", "b", "c", "d", "e", "f"])
        + _walk(["a", "b", "c"], start="2026-07-27 12:00:00", uuid="u2", suid="s2")
        + _walk(["c", "d", "e"], start="2026-07-27 14:00:00", uuid="u3", suid="s3")
    )
    cut = _run(rows, top_n=1)
    tail = cut[(cut["n"] == 3) & (cut["path"] == OTHER_PATH)].iloc[0]
    assert int(tail["distinct_dropped"]) == 3
    assert int(tail["cnt"]) == 4


def test_the_kept_rows_report_zero_dropped():
    rows = _walk(["a", "b", "c", "d"])
    got = _run(rows, top_n=1)
    kept = got[(got["n"] == 3) & (got["path"] != OTHER_PATH)]
    assert set(kept["distinct_dropped"]) == {0}


def test_the_cut_is_deterministic_when_counts_tie():
    """`ORDER BY cnt DESC` 만이면 동수인 경로 중 누가 남는지 실행마다 바뀐다.

    `path` tie-break 가 있으면 사전순으로 앞선 것이 남는다 — 같은 입력에서 같은 큐브다.
    """
    rows = _walk(["a", "b", "c", "d"])  # a>b>c, b>c>d 둘 다 1회
    seen = set()
    for _ in range(5):
        paths = _paths(_run(rows, top_n=1), 3)
        # `(other)` 행도 함께 나오므로 빼고 본다 — 남은 경로가 무엇인지가 요점이다.
        seen.update(p for p in paths if p != OTHER_PATH)
    assert seen == {"top/a>top/b>top/c"}


def test_the_screen_outside_the_dictionary_folds_to_service_other():
    got = _paths(_run(_walk(["a", "사전에_없는_화면", "c"])), 3)
    assert got == {"top/a>top/other>top/c": 1}


def test_a_session_starting_on_an_earlier_day_is_excluded():
    rows = _walk(["a", "b", "c"], start="2026-07-26 23:50:00")
    assert _run(rows).empty


def test_a_click_does_not_become_a_screen_in_the_path():
    """경로는 Pageview 만으로 만든다 — 클릭이 섞이면 걸음 수가 부푼다."""
    rows = _walk(["a", "b", "c"])
    click = dict(rows[0])
    click["ts"] = pd.Timestamp("2026-07-27 10:00:30")
    click["action_type"] = "Event"
    click["action_kind"] = "ClickContent"
    click["layer1"] = "home_main"
    assert _paths(_run(rows + [click]), 3) == {"top/a>top/b>top/c": 1}
