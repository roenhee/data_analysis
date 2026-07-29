"""큐브 빌드 오케스트레이션.

1단계: state 사전을 기간 전체 기준으로 확정하고 저장한다.
2단계: 사전을 고정한 채 날짜별로 큐브를 빌드한다. 이미 있는 (날짜, 캐시키) 조합은
       건너뛰므로 나중에 날짜를 추가해도 앞선 날짜를 다시 만들지 않는다.

`query_fn(sql) -> DataFrame` 이 유일한 서버 I/O 심(seam)이다. 테스트에서 대체한다.
"""
from __future__ import annotations

from datetime import date as _date
from datetime import timedelta
from pathlib import Path

import pandas as pd

from analytics.cube.axes import CORE_AXIS_NAMES
from analytics.cube.guard import assert_safe_sql
from analytics.cube.sql import (
    build_quality_cube_sql,
    build_session_cube_sql,
    build_transition_cube_sql,
)
from analytics.cube.state_dict import (
    DEFAULT_CUT_RATIO,
    DEFAULT_MIN_COUNT,
    StateDict,
    apply_cut,
    save_state_dict,
)
from analytics.cube.state_sql import (
    build_layer1_count_sql,
    build_layer2_count_sql,
    build_screen_count_sql,
    build_version_count_sql,
)
from analytics.cube.store import has_cube, write_cube
from data_layer.config import Config
from data_layer.util import content_hash, day_strings

SOURCES_PATH = Path("examples/config/sources.json")

# `sources.json` 의 좌표와 반드시 같아야 한다 — 갈라지면 `source_version` 만 새로워지고
# 쿼리는 옛 테이블을 읽어 새 캐시 키 아래 옛 데이터가 앉는다.
# `test_table_constants_match_sources_json` 이 이 일치를 지킨다.
EVENTS_TABLE = "bigdata_omega_common_iceberg.axz_tiara.all_tiara_n"
DEMOGRAPHY_TABLE = "hadoop_doopey.target_subcom.tb_axz_demography_uuid_v2"

# 앱버전 축이 가질 수 있는 최대 값 수. 넘치는 버전은 `app_version_expr` 이 'other' 로
# 접으므로 합계는 보존된다 — 사라지는 것은 라벨뿐이다.
MAX_APP_VERSIONS = 16


def _default_query(sql: str) -> pd.DataFrame:
    """실 Trino 실행.

    접속 로직은 `data_layer.fetch_aggregate` 의 것을 그대로 쓴다. 복사본을 두면
    한쪽만 고쳐지는 날이 온다.
    """
    from data_layer.fetch_aggregate import _default_query as run_on_source
    from data_layer.sources import load_sources

    return run_on_source(load_sources(SOURCES_PATH)["events"], sql)


def _run(query_fn, sql: str) -> pd.DataFrame:
    assert_safe_sql(sql)
    return query_fn(sql)


# 로직 지문을 뽑을 때만 쓰는 고정 날짜. 실제 빌드에는 쓰이지 않는다.
# 날짜를 고정해야 같은 로직이 날짜마다 다른 캐시 키를 내지 않는다.
_KEY_PROBE_DATE = "2000-01-01"


def _logic_hash(cube_builder, *, state_dict, services, events_table,
                demography_table) -> str:
    """큐브 SQL의 로직 지문. 캐시 키에 들어간다.

    이게 키에 없으면 집계 SQL을 고쳐도 키가 그대로라 다시 빌드해도 **옛 큐브가 캐시
    적중으로 나온다.** 로직을 고쳤는데 결과가 안 바뀌고 그걸 눈치채지 못하는 상태다.
    수동으로 올리는 버전 상수를 쓰지 않는 이유는 올리는 걸 잊기 때문이다.

    날짜만 고정하고 나머지는 실제 인자로 SQL을 만들어 해싱한다. 따라서 지문은 날짜
    간에는 같고, 집계 로직·서비스 목록·state 사전·테이블 좌표가 바뀌면 달라진다.
    (서비스 목록은 키의 다른 어떤 항목에도 들어있지 않아서, 이 지문이 서비스별 큐브가
    같은 경로에 겹쳐 쓰이는 것도 함께 막는다.)
    """
    probe = cube_builder(
        state_dict=state_dict,
        date=_KEY_PROBE_DATE,
        services=services,
        events_table=events_table,
        demography_table=demography_table,
    )
    return content_hash(probe)


def cube_key_parts(
    cube_name: str,
    *,
    state_dict,
    services: list[str],
    source_version: str,
    cube_builders: dict | None = None,
    events_table: str = EVENTS_TABLE,
    demography_table: str = DEMOGRAPHY_TABLE,
) -> dict:
    """큐브 하나의 캐시 키 부품. **쓰는 쪽과 읽는 쪽이 같이 쓴다.**

    키를 두 곳에서 따로 조립하면 한쪽만 고쳐졌을 때 읽기가 조용히 아무것도 못 찾거나,
    더 나쁘게는 다른 로직으로 만든 큐브를 집어온다. `sql_hash` 가 큐브마다 다르므로
    호출자가 손으로 채울 수 있는 값도 아니다 — 사전·서비스·테이블 좌표까지 들어간다.
    """
    builders = cube_builders or DEFAULT_CUBE_BUILDERS
    if cube_name not in builders:
        raise KeyError(
            f"no such cube: {cube_name!r}; known: {', '.join(sorted(builders))}"
        )
    return dict(
        source_version=source_version,
        state_dict_version=state_dict.version(),
        axes=CORE_AXIS_NAMES,
        cube_name=cube_name,
        sql_hash=_logic_hash(
            builders[cube_name], state_dict=state_dict, services=services,
            events_table=events_table, demography_table=demography_table,
        ),
    )


def build_state_dict(
    config: Config,
    window: tuple[str, str],
    services: list[str],
    cut_ratio: float = DEFAULT_CUT_RATIO,
    min_count: int = DEFAULT_MIN_COUNT,
    query_fn=None,
    events_table: str = EVENTS_TABLE,
) -> StateDict:
    """1단계. 기간 전체를 한 번 훑어 채택 목록을 확정하고 저장한다."""
    q = query_fn or _default_query
    screens = apply_cut(
        _run(q, build_screen_count_sql(events_table, window, services)),
        cut_ratio, min_count,
    )
    layer1 = apply_cut(
        _run(q, build_layer1_count_sql(events_table, window, services)),
        cut_ratio, min_count,
    )
    layer2 = apply_cut(
        _run(q, build_layer2_count_sql(events_table, window, services)),
        cut_ratio, min_count,
    )
    versions = apply_cut(
        _run(q, build_version_count_sql(events_table, window, services)),
        cut_ratio, min_count,
    )[:MAX_APP_VERSIONS]
    sd = StateDict(
        screens=screens, layer1=layer1, layer2=layer2, app_versions=versions,
        cut_ratio=cut_ratio, min_count=min_count,
    )
    save_state_dict(config, sd)
    return sd


def _window_dates(day: str) -> list[str]:
    """세션 귀속용 읽기 창 `[D-1, D, D+1]`.

    `D+1` 은 자정을 넘긴 세션의 꼬리를 확보하고, `D-1` 은 중복 집계를 막는다.
    """
    d = _date.fromisoformat(day)
    return [
        (d - timedelta(days=1)).isoformat(),
        day,
        (d + timedelta(days=1)).isoformat(),
    ]


def _session_builder(*, state_dict, date, services, events_table, demography_table, **_):
    return build_session_cube_sql(
        events_table=events_table, demography_table=demography_table,
        date=date, window_dates=_window_dates(date), services=services,
        versions=state_dict.app_versions,
    )


def _transition_builder(
    *, state_dict, date, services, events_table, demography_table, **_
):
    return build_transition_cube_sql(
        events_table=events_table, demography_table=demography_table,
        date=date, window_dates=_window_dates(date), services=services,
        versions=state_dict.app_versions, screens=state_dict.screens,
    )


def _quality_builder(*, date, services, events_table, **_):
    # 세션 단위 검사가 자정을 넘긴 세션을 보려면 다른 큐브와 같은 창이 필요하다.
    return build_quality_cube_sql(
        events_table=events_table, date=date,
        window_dates=_window_dates(date), services=services,
    )


DEFAULT_CUBE_BUILDERS = {
    "session": _session_builder,
    "transition": _transition_builder,
    "quality": _quality_builder,
}


def build_cubes(
    config: Config,
    state_dict: StateDict,
    window: tuple[str, str],
    services: list[str],
    source_version: str,
    query_fn=None,
    refresh: bool = False,
    cube_builders: dict | None = None,
    events_table: str = EVENTS_TABLE,
    demography_table: str = DEMOGRAPHY_TABLE,
) -> list[Path]:
    """2단계. 날짜별로 큐브를 빌드한다. 이미 있는 조합은 건너뛴다.

    **실패하면 그 자리에서 멈춘다.** 앞서 완성된 날짜의 parquet 은 그대로 남고, 실패한
    날짜와 그 뒤는 미기록으로 남는다. 재실행하면 남은 것을 건너뛰고 실패분부터 이어서
    시도한다. 실패를 삼키고 계속 가지 않는 이유는, 여기서 실패하는 원인(접속 끊김·권한·
    스키마 변경)이 대개 뒤 날짜에도 그대로 적용되기 때문이다 — 30일을 헛돌 이유가 없다.
    """
    q = query_fn or _default_query
    builders = cube_builders or DEFAULT_CUBE_BUILDERS
    # 날짜와 무관하므로 날짜 루프 밖에서 한 번만 계산한다.
    keys = {
        name: cube_key_parts(
            name, state_dict=state_dict, services=services,
            source_version=source_version, cube_builders=builders,
            events_table=events_table, demography_table=demography_table,
        )
        for name in builders
    }
    written: list[Path] = []
    for day in day_strings(*window):
        for name, builder in builders.items():
            key_parts = keys[name]
            if not refresh and has_cube(config, date=day, **key_parts):
                continue
            sql = builder(
                state_dict=state_dict, date=day, services=services,
                events_table=events_table, demography_table=demography_table,
            )
            df = _run(q, sql)
            written.append(write_cube(config, df, date=day, **key_parts))
    return written
