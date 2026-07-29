"""큐브 로딩과 부분 빌드 감지.

`metrics/` 에서 **파일시스템을 아는 유일한 모듈**이다. 수식 모듈은 프레임만 받는다.

`store.read_cube` 는 요청 날짜가 전부 없으면 예외를 내지만 **일부만 없으면 있는 것만
조용히 읽는다**(부분 빌드 상태에서도 읽을 수 있어야 하므로 의도된 동작이다). 그래서
30일을 요청해 3일을 받은 호출자는 아무 신호 없이 틀린 분모로 계산한다. 그 조용함을
여기서 끝낸다.
"""
from __future__ import annotations

from dataclasses import dataclass

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
