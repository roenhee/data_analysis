"""큐브 parquet의 캐시 키와 경로 규약.

캐시 키에 source/state 사전/축/큐브명을 모두 넣으므로, 어느 하나가 달라지면 다른
파일이 된다. 조용한 덮어쓰기가 구조적으로 불가능하다.
"""
from __future__ import annotations

from pathlib import Path

import duckdb
import pandas as pd

from data_layer.config import Config
from data_layer.util import content_hash


def cube_key(
    source_version: str,
    state_dict_version: str,
    axes: tuple[str, ...],
    cube_name: str,
) -> str:
    return content_hash(source_version, state_dict_version, list(axes), cube_name)


def cube_dir(
    config: Config,
    source_version: str,
    state_dict_version: str,
    axes: tuple[str, ...],
    cube_name: str,
) -> Path:
    key = cube_key(source_version, state_dict_version, axes, cube_name)
    return config.root / "cubes" / cube_name / key


def cube_path(
    config: Config,
    date: str,
    source_version: str,
    state_dict_version: str,
    axes: tuple[str, ...],
    cube_name: str,
) -> Path:
    d = cube_dir(config, source_version, state_dict_version, axes, cube_name)
    return d / f"date={date}.parquet"


def has_cube(config: Config, date: str, **key_parts) -> bool:
    return cube_path(config, date=date, **key_parts).exists()


def write_cube(config: Config, df: pd.DataFrame, date: str, **key_parts) -> Path:
    path = cube_path(config, date=date, **key_parts)
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path, index=False)
    return path


class CubeNotBuiltError(FileNotFoundError):
    """요청한 날짜의 큐브가 하나도 없다."""


def read_cube(config: Config, dates: list[str], **key_parts) -> pd.DataFrame:
    """요청한 날짜들의 큐브를 하나의 DataFrame으로 읽는다.

    일부 날짜가 없으면 있는 것만 읽는다 — 부분 빌드 상태에서도 읽을 수 있어야 한다.
    무엇이 빠졌는지는 호출자가 `has_cube` 로 확인한다.

    **요청한 날짜가 전부 없으면 `CubeNotBuiltError` 를 낸다.** 빈 DataFrame을 돌려주면
    "큐브를 안 만들었다"와 "그 세그먼트에 데이터가 없다"가 구분되지 않는다. 전자는
    파이프라인 공백(에러)이고 후자는 결과(사실)인데, 둘을 같은 값으로 표현하면 대시보드가
    미빌드 구간을 '0'으로 보고한다. 조용히 틀린 숫자를 내지 않는다는 원칙에 어긋난다.
    """
    paths = [
        str(cube_path(config, date=d, **key_parts))
        for d in dates
        if has_cube(config, date=d, **key_parts)
    ]
    if not paths:
        raise CubeNotBuiltError(
            f"no cube built for {key_parts.get('cube_name')!r} on any of {dates}; "
            "build it first — an empty frame here would be indistinguishable from "
            "a segment that genuinely has no data"
        )
    con = duckdb.connect()
    try:
        return con.execute(
            "SELECT * FROM read_parquet($paths)", {"paths": paths}
        ).df()
    finally:
        con.close()
