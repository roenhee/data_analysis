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


def read_cube(config: Config, dates: list[str], **key_parts) -> pd.DataFrame:
    """요청한 날짜들의 큐브를 하나의 DataFrame으로 읽는다.

    빌드되지 않은 날짜는 조용히 건너뛴다 — 부분 빌드 상태에서도 있는 만큼 읽을 수
    있어야 한다. 무엇이 없는지는 호출자가 `has_cube` 로 확인한다.
    """
    paths = [
        str(cube_path(config, date=d, **key_parts))
        for d in dates
        if has_cube(config, date=d, **key_parts)
    ]
    if not paths:
        return pd.DataFrame()
    con = duckdb.connect()
    try:
        return con.execute(
            "SELECT * FROM read_parquet($paths)", {"paths": paths}
        ).df()
    finally:
        con.close()
