import json
from pathlib import Path

import pandas as pd
import pytest

from analytics.cube.builder import (
    DEMOGRAPHY_TABLE,
    EVENTS_TABLE,
    SOURCES_PATH,
    build_cubes,
    build_state_dict,
)
from analytics.cube.guard import GuardError
from analytics.cube.state_dict import StateDict


class FakeQuery:
    """SQL 문자열로 어떤 집계인지 판별해 가짜 결과를 준다."""

    def __init__(self):
        self.calls = []

    def __call__(self, sql):
        self.calls.append(sql)
        if "AS value" in sql:
            if "click.layer1" in sql and "'>'" in sql:
                return pd.DataFrame({"value": ["home_main>SLOT"], "cnt": [50_000]})
            if "click.layer1" in sql:
                return pd.DataFrame({"value": ["home_main"], "cnt": [90_000]})
            if "env.app_version" in sql:
                return pd.DataFrame(
                    {"value": ["9.5.1", "9.5.0"], "cnt": [80_000, 20_000]}
                )
            return pd.DataFrame({"value": ["top/홈탭_진입"], "cnt": [70_000]})
        if "AS sessions" in sql:
            return pd.DataFrame({"period": ["2026-07-27"], "sessions": [10], "uv": [8]})
        # **순서가 중요하다.** `cond_transition` 도 `from_state` 를 갖고 있어서 전이 큐브
        # 분기가 앞에 오면 그쪽 결과를 받는다. 세 개를 각자만 가진 표식으로 먼저 가른다.
        if "distinct_dropped" in sql:
            return pd.DataFrame(
                {"n": [3, 3], "path": ["a>b>c", "(other)"], "cnt": [7, 3],
                 "distinct_dropped": [0, 12]}
            )
        if "c.action_kind" in sql:
            return pd.DataFrame(
                {"screen": ["top/홈탭_진입"], "action_kind": ["ClickContent"],
                 "layer1": ["home_main"], "layer2": ["other"], "cnt": [9]}
            )
        if "p.action_kind" in sql:
            return pd.DataFrame(
                {"from_state": ["top/홈탭_진입"], "action_kind": ["ClickContent"],
                 "to_state": ["EXIT"], "cnt": [4]}
            )
        if "AS cnt" in sql and "from_state" in sql:
            return pd.DataFrame(
                {"from_state": ["START"], "to_state": ["top/홈탭_진입"], "cnt": [5]}
            )
        return pd.DataFrame(
            {"check_name": ["null_action_name"], "violated": [1], "total": [10]}
        )


def _sd(**over) -> StateDict:
    base = dict(
        screens=["top/홈탭_진입"], layer1=["home_main"], layer2=[],
        app_versions=["9.5.1"], cut_ratio=0.95, min_count=10_000,
    )
    return StateDict(**{**base, **over})


def test_build_state_dict_applies_the_cut_and_returns_a_versioned_dict(config):
    q = FakeQuery()
    sd = build_state_dict(
        config, window=("2026-07-27", "2026-07-27"), services=["top"], query_fn=q
    )
    assert isinstance(sd, StateDict)
    assert sd.screens == ["top/홈탭_진입"]
    assert sd.app_versions == ["9.5.1", "9.5.0"]
    assert sd.version().startswith("sd_")


def test_build_state_dict_persists_it(config):
    sd = build_state_dict(
        config, window=("2026-07-27", "2026-07-27"), services=["top"],
        query_fn=FakeQuery(),
    )
    assert (config.root / "state_dicts" / f"{sd.version()}.json").exists()


def test_build_cubes_writes_one_file_per_cube_per_date(config):
    written = build_cubes(
        config, state_dict=_sd(), window=("2026-07-27", "2026-07-28"),
        services=["top"], source_version="sv1", query_fn=FakeQuery(),
    )
    assert len(written) == 12  # 6 큐브 x 2 날짜
    for path in written:
        assert path.exists()


def test_builds_six_cubes_per_date(config):
    written = build_cubes(
        config, state_dict=_sd(), window=("2026-07-27", "2026-07-27"),
        services=["top"], source_version="sv1", query_fn=FakeQuery(),
    )
    assert len(written) == 6
    assert {p.parent.parent.name for p in written} == {
        "session", "transition", "quality", "action", "cond_transition", "path",
    }


def test_every_builder_reads_the_same_three_partition_window():
    """창이 갈리면 자정 넘긴 세션이 큐브마다 다르게 잘려 큐브 간 조인이 조용히 어긋난다.

    `D+1` 은 자정 넘긴 세션의 꼬리를, `D-1` 은 중복 집계 방지를 위한 것이므로 여섯 큐브가
    모두 `[D-1, D, D+1]` 을 읽어야 한다. 하나만 `[D]` 로 좁혀도 예외는 나지 않는다.
    """
    from analytics.cube.builder import DEFAULT_CUBE_BUILDERS

    expected = "date_id IN ('2026-07-26', '2026-07-27', '2026-07-28')"
    for name, builder in DEFAULT_CUBE_BUILDERS.items():
        sql = builder(
            state_dict=_sd(), date="2026-07-27", services=["top"],
            events_table=EVENTS_TABLE, demography_table=DEMOGRAPHY_TABLE,
        )
        assert expected in sql, name


def test_every_screen_cube_receives_the_dictionary():
    """사전을 안 넘기면 모든 화면이 `/other` 로 접히는데 예외는 나지 않는다.

    화면을 쓰는 네 큐브(`transition`·`action`·`cond_transition`·`path`)가 같은 어휘를
    받아야 서로 조인된다. 하나만 빈 목록을 받으면 그 큐브만 이름 없는 상태로 채워진다.
    """
    from analytics.cube.builder import DEFAULT_CUBE_BUILDERS

    sd = _sd(screens=["top/홈탭_진입"])
    for name in ("transition", "action", "cond_transition", "path"):
        sql = DEFAULT_CUBE_BUILDERS[name](
            state_dict=sd, date="2026-07-27", services=["top"],
            events_table=EVENTS_TABLE, demography_table=DEMOGRAPHY_TABLE,
        )
        assert "'top/홈탭_진입'" in sql, name


def test_the_action_cube_receives_both_layer_dictionaries():
    """`layer1`·`layer2` 를 안 넘기면 슬롯 좌표가 전부 `other` 가 된다."""
    from analytics.cube.builder import DEFAULT_CUBE_BUILDERS

    sd = _sd(layer1=["home_main"], layer2=["home_main>SEARCH"])
    sql = DEFAULT_CUBE_BUILDERS["action"](
        state_dict=sd, date="2026-07-27", services=["top"],
        events_table=EVENTS_TABLE, demography_table=DEMOGRAPHY_TABLE,
    )
    assert "'home_main'" in sql
    assert "'home_main>SEARCH'" in sql


def test_every_builder_shares_the_first_event_attribution():
    """귀속이 갈라지면 같은 세션이 큐브마다 다른 날짜·축 버킷에 앉는다."""
    from analytics.cube.builder import DEFAULT_CUBE_BUILDERS
    from analytics.cube.sql import _first_event_attribution

    clause = _first_event_attribution("2026-07-27")
    for name, builder in DEFAULT_CUBE_BUILDERS.items():
        sql = builder(
            state_dict=_sd(), date="2026-07-27", services=["top"],
            events_table=EVENTS_TABLE, demography_table=DEMOGRAPHY_TABLE,
        )
        if name == "quality":
            continue  # 품질 큐브는 세션 검사마다 자체 집계를 쓴다
        assert clause in sql, name


def test_adding_the_new_cubes_does_not_rebuild_the_old_ones(config):
    """새 큐브를 붙여도 기존 세 큐브는 캐시 적중이어야 한다.

    `sql_hash` 가 **큐브별**이라 성립한다(`cube_key_parts`). 안 그러면 15일 백필을 다시
    돌려야 하고, 사전 버전이 같아도 좌표가 흔들린다.
    """
    from analytics.cube.builder import DEFAULT_CUBE_BUILDERS

    old = ("session", "transition", "quality")
    kw = dict(config=config, state_dict=_sd(), window=("2026-07-27", "2026-07-27"),
              services=["top"], source_version="sv1")
    first = build_cubes(**kw, query_fn=FakeQuery(),
                        cube_builders={k: DEFAULT_CUBE_BUILDERS[k] for k in old})
    assert len(first) == 3
    before = {p: p.stat().st_mtime_ns for p in first}

    second = FakeQuery()
    written = build_cubes(**kw, query_fn=second)
    assert len(written) == 3, "새 큐브 셋만 만들어져야 한다"
    for path, mtime in before.items():
        assert path.stat().st_mtime_ns == mtime, f"{path} 가 다시 만들어졌다"


def test_build_cubes_skips_dates_already_built(config):
    kw = dict(config=config, state_dict=_sd(screens=["s"], layer1=[]),
              window=("2026-07-27", "2026-07-27"),
              services=["top"], source_version="sv1")
    build_cubes(**kw, query_fn=FakeQuery())
    second = FakeQuery()
    written = build_cubes(**kw, query_fn=second)
    assert written == []
    assert second.calls == []


def test_build_cubes_refresh_rebuilds(config):
    kw = dict(config=config, state_dict=_sd(screens=["s"], layer1=[]),
              window=("2026-07-27", "2026-07-27"),
              services=["top"], source_version="sv1")
    build_cubes(**kw, query_fn=FakeQuery())
    written = build_cubes(**kw, query_fn=FakeQuery(), refresh=True)
    assert len(written) == 6


def test_build_cubes_rejects_unpruned_sql(config):
    def bad_builder(**kwargs):
        return "SELECT 1"

    with pytest.raises(GuardError):
        build_cubes(
            config, state_dict=_sd(screens=["s"], layer1=[], app_versions=[]),
            window=("2026-07-27", "2026-07-27"),
            services=["top"], source_version="sv1", query_fn=FakeQuery(),
            cube_builders={"broken": bad_builder},
        )


def test_table_constants_match_sources_json():
    """빌더의 좌표와 `sources.json` 이 갈라지면 조용히 틀린 테이블을 읽는다.

    `source_version` 은 `sources.json` 에서 나오므로 좌표만 바뀌면 캐시 키는 새로워지는데
    실제 쿼리는 옛 테이블을 그대로 읽는다 — 새 키 아래 옛 데이터가 앉는다.
    """
    raw = {s["id"]: s for s in json.loads(Path(SOURCES_PATH).read_text())}
    for src_id, constant in (
        ("events", EVENTS_TABLE),
        ("demography", DEMOGRAPHY_TABLE),
    ):
        s = raw[src_id]
        assert constant == f"{s['catalog']}.{s['schema']}.{s['table']}"


def test_quality_cube_reads_the_three_partition_window(config):
    # 세션 검사가 자정 횡단 세션을 보려면 창이 필요하다 — Task 11 참조.
    q = FakeQuery()
    build_cubes(
        config, state_dict=_sd(), window=("2026-07-27", "2026-07-27"),
        services=["top"], source_version="sv1", query_fn=q,
    )
    quality = [s for s in q.calls if "check_name" in s]
    assert len(quality) == 1
    assert "date_id IN ('2026-07-26', '2026-07-27', '2026-07-28')" in quality[0]


def test_cube_builders_use_the_tables_they_are_given(config):
    q = FakeQuery()
    build_cubes(
        config, state_dict=_sd(), window=("2026-07-27", "2026-07-27"),
        services=["top"], source_version="sv1", query_fn=q,
        events_table="cat.sch.ev", demography_table="cat.sch.dem",
    )
    assert all("cat.sch.ev" in s for s in q.calls)
    assert any("cat.sch.dem" in s for s in q.calls)


def _pruned(tail: str = ""):
    """가드를 통과하는 최소 SQL 을 내는 빌더. `tail` 로 로직만 바꿔치기한다."""
    def _b(*, date, services, **_):
        return (
            f"SELECT 1 AS cnt{tail}\n"
            "FROM t\n"
            f"WHERE date_id = '{date}' AND c_service_code = '{services[0]}'\n"
        )
    return _b


def test_changing_the_aggregation_sql_misses_the_cache(config):
    """집계 SQL이 바뀌면 반드시 다시 빌드해야 한다.

    SQL 로직이 캐시 키에 없던 동안에는 `dur_sum` 을 고치고 다시 빌드해도 옛 큐브가
    그대로 나왔다. 로직을 고쳤는데 결과가 안 바뀌고 그걸 눈치채지 못하는 상태였다.
    """
    kw = dict(config=config, state_dict=_sd(), window=("2026-07-27", "2026-07-27"),
              services=["top"], source_version="sv1")
    first = build_cubes(**kw, query_fn=FakeQuery(), cube_builders={"c": _pruned()})
    assert len(first) == 1

    again = build_cubes(**kw, query_fn=FakeQuery(), cube_builders={"c": _pruned()})
    assert again == [], "같은 SQL 은 캐시 적중이어야 한다"

    changed = build_cubes(
        **kw, query_fn=FakeQuery(), cube_builders={"c": _pruned(", 2 AS extra")}
    )
    assert len(changed) == 1, "SQL 이 바뀌었는데 캐시 적중했다"
    assert changed[0] != first[0], "새 로직이 옛 큐브를 덮어썼다"


def test_changing_one_cube_does_not_rebuild_the_others(config):
    """지문은 큐브별로 따로다.

    그래서 quality SQL 만 고치면 다시 돌렸을 때 quality 만 새로 만들어진다 —
    session·transition 은 키가 그대로라 캐시 적중이다. 전체 백필을 다시 돌릴 필요가 없다.
    """
    kw = dict(config=config, state_dict=_sd(), window=("2026-07-27", "2026-07-27"),
              services=["top"], source_version="sv1")
    first = build_cubes(**kw, query_fn=FakeQuery(), cube_builders={
        "session": _pruned(), "transition": _pruned(", 2 AS x"),
        "quality": _pruned(", 3 AS y"),
    })
    assert len(first) == 3

    # quality 만 고친다
    second = build_cubes(**kw, query_fn=FakeQuery(), cube_builders={
        "session": _pruned(), "transition": _pruned(", 2 AS x"),
        "quality": _pruned(", 9 AS z"),
    })
    assert len(second) == 1, "바뀌지 않은 큐브까지 다시 만들었다"
    assert "/quality/" in str(second[0])


def test_the_logic_fingerprint_is_the_same_across_dates(config):
    """지문이 날짜에 흔들리면 날짜마다 다른 디렉터리가 생겨 범위 읽기가 깨진다."""
    kw = dict(config=config, state_dict=_sd(), services=["top"], source_version="sv1")
    written = build_cubes(**kw, window=("2026-07-27", "2026-07-29"),
                          query_fn=FakeQuery(), cube_builders={"c": _pruned()})
    assert len({p.parent for p in written}) == 1
    assert len(written) == 3


def test_different_services_do_not_share_a_cube_path(config):
    """서비스 목록은 키의 다른 어떤 항목에도 없다 — 지문이 겹침을 막는 유일한 장치다."""
    kw = dict(config=config, state_dict=_sd(), window=("2026-07-27", "2026-07-27"),
              source_version="sv1", cube_builders={"c": _pruned()})
    top = build_cubes(**kw, services=["top"], query_fn=FakeQuery())
    media = build_cubes(**kw, services=["media"], query_fn=FakeQuery())
    assert top[0] != media[0]


def test_a_failing_date_leaves_earlier_dates_committed(config):
    """날짜 하나가 실패해도 앞서 성공한 날짜의 parquet 은 남는다.

    재실행하면 남은 것은 건너뛰고 실패분부터 다시 시도한다.
    """
    class FailsOnSecondDate(FakeQuery):
        def __call__(self, sql):
            # 창에는 이웃 날짜가 들어 있으므로 창이 아니라 **귀속 절**로 판별한다.
            if "date('2026-07-28')" in sql:
                raise RuntimeError("트리노 죽음")
            return super().__call__(sql)

    with pytest.raises(RuntimeError):
        build_cubes(
            config, state_dict=_sd(), window=("2026-07-27", "2026-07-28"),
            services=["top"], source_version="sv1", query_fn=FailsOnSecondDate(),
        )
    resumed = build_cubes(
        config, state_dict=_sd(), window=("2026-07-27", "2026-07-28"),
        services=["top"], source_version="sv1", query_fn=FakeQuery(),
    )
    # 27일치 6개는 이미 있으므로 28일치 6개만 새로 쓴다.
    assert len(resumed) == 6
    assert all("date=2026-07-28" in p.name for p in resumed)
