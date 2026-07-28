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
    assert len(written) == 6  # 3 큐브 x 2 날짜
    for path in written:
        assert path.exists()


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
    assert len(written) == 3


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
    # 27일치 3개는 이미 있으므로 28일치 3개만 새로 쓴다.
    assert len(resumed) == 3
    assert all("date=2026-07-28" in p.name for p in resumed)
