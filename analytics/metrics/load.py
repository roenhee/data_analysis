"""큐브 로딩과 부분 빌드 감지.

`metrics/` 에서 **파일시스템을 아는 유일한 모듈**이다. 수식 모듈은 프레임만 받는다.

`store.read_cube` 는 요청 날짜가 전부 없으면 예외를 내지만 **일부만 없으면 있는 것만
조용히 읽는다**(부분 빌드 상태에서도 읽을 수 있어야 하므로 의도된 동작이다). 그래서
30일을 요청해 3일을 받은 호출자는 아무 신호 없이 틀린 분모로 계산한다. 그 조용함을
여기서 끝낸다.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from analytics.cube.store import has_cube, read_cube
from data_layer.config import Config


class IncompleteCubeError(RuntimeError):
    """요청한 날짜 중 일부가 빌드되지 않았다."""


@dataclass(frozen=True)
class LoadedCube:
    """읽은 프레임과 **무엇을 못 읽었는지**를 함께 들고 다닌다."""

    frame: pd.DataFrame
    requested_dates: list[str]
    present_dates: list[str]
    missing_dates: list[str]

    @property
    def is_complete(self) -> bool:
        return not self.missing_dates

    def require_complete(self) -> "LoadedCube":
        """비율·평균·확률을 내기 전에 호출한다. 스펙상 권고가 아니라 요건이다."""
        if self.missing_dates:
            raise IncompleteCubeError(
                f"{len(self.missing_dates)}/{len(self.requested_dates)} dates are "
                f"not built: {', '.join(self.missing_dates)}; build them first — "
                "computing a ratio over a partial window yields a plausible number "
                "with the wrong denominator"
            )
        return self


HOLIDAYS_PATH = Path("examples/config/holidays_kr.json")


def load_holidays(path: Path = HOLIDAYS_PATH) -> tuple[set[str], list[tuple[str, str]]]:
    """공휴일 집합과 **검증된 구간** 목록을 돌려준다.

    검증 구간을 함께 내는 이유는 목록이 불완전하기 때문이다 — 음력 공휴일과 대체공휴일은
    자동 계산하지 않는다. `calendar.split_by_kind(..., verified=...)` 에 그대로 넘기면
    목록이 미검증인 구간의 날짜를 조용히 '평일' 로 세지 않는다.
    """
    raw = json.loads(Path(path).read_text())
    windows = [(a, b) for a, b in raw.get("verified_windows", [])]
    return set(raw.get("holidays", {})), windows


RELEASES_PATH = Path("examples/config/releases.json")


def load_releases(path: Path = RELEASES_PATH) -> dict[str, str]:
    """`{버전: 배포일}`. `compare` 가 배포 전 날짜를 제외하는 데 쓴다.

    배포 전 트래픽은 **다른 모집단**(테스터)이라 적은 표본과 다르다. 등록되지 않은
    버전은 막지 않는다 — 그 경우 `day_volumes` 를 보고 사람이 판단한다.
    """
    raw = json.loads(Path(path).read_text())
    return {
        version: meta["released"]
        for version, meta in raw.get("app_versions", {}).items()
        if meta.get("released")
    }


def load_cube(config: Config, dates: list[str], **key_parts) -> LoadedCube:
    """요청 날짜를 읽고 빠진 날짜를 함께 돌려준다.

    하나도 빌드되지 않았으면 `read_cube` 가 `CubeNotBuiltError` 를 낸다 — 빈 프레임은
    "안 만들었다"와 "그 세그먼트에 데이터가 없다"를 구분하지 못한다.
    """
    requested = sorted(set(dates))
    present = [d for d in requested if has_cube(config, date=d, **key_parts)]
    missing = [d for d in requested if d not in present]
    frame = read_cube(config, dates=present or requested, **key_parts)
    return LoadedCube(
        frame=frame,
        requested_dates=requested,
        present_dates=present,
        missing_dates=missing,
    )
