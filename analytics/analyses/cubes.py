"""`CubeSet` 로딩. 분석층에서 **파일시스템을 아는 유일한 모듈**이다.

`metrics/load.py` 위에 얹는다(아래가 아니다) — `CubeSet` 이 이 층의 타입이므로 아래
층이 그걸 알면 의존이 순환한다.

**손으로 조립하지 말 것.** `CubeSet` 은 필드가 7개고, 그중 `present_dates` 를 요청
날짜로 채우면 봉투가 부분 빌드를 완전하다고 보고한다. `state_dict_version` 을 잘못
넣으면 발행물이 다른 사전 버전으로 기록된다. 둘 다 예외 없이 조용히 틀린다.
"""
from __future__ import annotations

import pandas as pd

from analytics.analyses.base import CubeSet
from analytics.cube.builder import (
    DEMOGRAPHY_TABLE,
    EVENTS_TABLE,
    SOURCES_PATH,
    cube_key_parts,
)
from analytics.cube.state_dict import load_state_dict
from analytics.metrics.load import IncompleteCubeError, load_cube
from data_layer.config import Config
from data_layer.sources import load_sources

DEFAULT_CUBE_NAMES = ("session", "transition", "quality")
# 3단계 행동층 큐브. **기본 목록에 넣지 않는다** — `path` 가 하루 136만 행(15.6 MB)이라
# 화면층만 보는 분석이 그걸 읽을 이유가 없다. 필요한 쪽이 `cube_names` 로 명시한다.
ACTION_LAYER_CUBE_NAMES = ("action", "cond_transition", "path")
ALL_CUBE_NAMES = DEFAULT_CUBE_NAMES + ACTION_LAYER_CUBE_NAMES


def load_cube_set(
    config: Config,
    dates: list[str],
    services: list[str],
    state_dict_version: str,
    cube_names: tuple[str, ...] = DEFAULT_CUBE_NAMES,
    require_complete: bool = True,
    source_version: str | None = None,
    events_table: str = EVENTS_TABLE,
    demography_table: str = DEMOGRAPHY_TABLE,
) -> CubeSet:
    """분석에 넘길 `CubeSet` 을 읽는다. Trino 를 건드리지 않는다.

    캐시 키는 **빌더와 같은 함수**(`cube_key_parts`)로 유도한다. `sql_hash` 가 큐브마다
    다르고 사전·서비스·테이블 좌표까지 들어가므로 호출자가 손으로 채울 수 있는 값이
    아니다 — 그래서 지금까지 이 층을 실제로 쓸 방법이 없었다.

    `present_dates` 는 요청한 큐브들의 **교집합**이고, 프레임도 그 날짜로 자른다.
    한 큐브라도 없는 날짜는 이 `CubeSet` 이 답할 수 없는 날짜인데, 프레임에 남겨 두면
    봉투가 "없다"고 적은 날짜의 행으로 숫자를 만들게 된다.

    `cube_names` 로 필요한 큐브만 받는다. 전이 큐브만 쓰는 분석이 품질 큐브의 빈 날짜
    때문에 좁아질 이유가 없다.

    `require_complete` 는 기본이 참이다 — 부분 창에서 낸 비율은 분모가 틀린 그럴듯한
    숫자다. 일부러 부분 창을 보려면 거짓으로 주고, 그때는 봉투의 `is_complete` 가
    거짓으로 실려 나간다.
    """
    requested = sorted(set(dates))
    state_dict = load_state_dict(config, state_dict_version)
    if source_version is None:
        source_version = load_sources(SOURCES_PATH)["events"].version()

    loaded = {}
    for name in cube_names:
        key = cube_key_parts(
            name, state_dict=state_dict, services=services,
            source_version=source_version, events_table=events_table,
            demography_table=demography_table,
        )
        loaded[name] = load_cube(config, dates=requested, **key)

    present = sorted(
        set.intersection(*(set(one.present_dates) for one in loaded.values()))
        if loaded else set()
    )
    missing = [d for d in requested if d not in set(present)]
    if require_complete and missing:
        raise IncompleteCubeError(
            f"{len(missing)}/{len(requested)} dates are not built in every requested "
            f"cube ({', '.join(cube_names)}): {', '.join(missing)}; build them first — "
            "computing a ratio over a partial window yields a plausible number with "
            "the wrong denominator"
        )

    def cut(frame: pd.DataFrame | None) -> pd.DataFrame | None:
        """빌드된 날짜의 행만 남긴다. `period` 가 NULL 인 행은 남긴다 — 날짜까지 접은
        `()` 롤업 행이고, 잘라내면 "기간 전체 `uv`" 를 읽을 행이 없어져 합산으로 때우게
        된다(실측 세션 큐브에서 15일치 15행이 사라졌다).
        """
        if frame is None or "period" not in frame.columns:
            return frame
        return frame[frame["period"].isna() | frame["period"].isin(present)]

    def frame_of(name: str) -> pd.DataFrame | None:
        return cut(loaded[name].frame) if name in loaded else None

    return CubeSet(
        session=frame_of("session"),
        transition=frame_of("transition"),
        quality=frame_of("quality"),
        state_dict_version=state_dict.version(),
        services=list(services),
        requested_dates=requested,
        present_dates=present,
        action=frame_of("action"),
        cond_transition=frame_of("cond_transition"),
        path=frame_of("path"),
    )
