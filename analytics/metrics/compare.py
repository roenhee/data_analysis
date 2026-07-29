"""세그먼트 비교의 교란 방지. 파일시스템도 config 도 모르는 순수 모듈.

**버전 델타는 이 프로젝트의 주 용도인데, 가장 조용히 틀리는 자리이기도 하다.**

앱 버전은 단계적으로 배포된다. 실측(2026-07-14~28, MA): `9.5.0` 은 07-14 에 2% 로 시작해
07-25 에 91% 에 이르고, `9.5.1` 은 07-26 에 2.1% 로 나타나 07-28 에 63.7% 가 된다. 즉 두
버전이 **같은 날짜 범위에 존재하지 않는다.**

그 상태로 "14일 전체" 를 비교하면 버전 차이가 아니라 **날짜 차이**를 재게 된다. 실측:

| 지표 | 14일 전체 | 겹치는 날짜만 |
|---|---|---|
| 기대 걸음 수 Δ | **+2.9%** | **-0.2%** |
| `top/홈탭_진입` 이탈 Δ | +0.39% | +0.77% |

"9.5.1 에서 세션이 2.9% 길어졌다" 는 그럴듯하고 완전히 틀린 결론이다. 예외도 안 나고
숫자도 멀쩡해 보인다. 그래서 `uv` 합산·부분 빌드와 같은 등급으로 **막는다.**
"""
from __future__ import annotations

import pandas as pd


class ConfoundedComparisonError(ValueError):
    """두 세그먼트가 같은 날짜 위에 없어 델타가 날짜 효과와 뒤섞인다."""


def _dates_of(cube: pd.DataFrame, axis: str, value: str) -> set[str]:
    if axis not in cube.columns:
        raise KeyError(f"no such column: {axis!r}")
    return set(cube.loc[cube[axis] == value, "period"].dropna())


def comparable_dates(cube: pd.DataFrame, axis: str, a: str, b: str) -> list[str]:
    """`a` 와 `b` 가 **둘 다** 존재하는 날짜. 없으면 거부한다.

    돌려주는 날짜 수가 적으면(1~2일) 요일 효과를 걷어내지 못하므로 호출자가 판단한다 —
    막지는 않되 몇 일인지는 보이게 한다.

    **물량은 여기서 보지 않는다.** 겹치는 날에 한쪽 버전의 점유율이 0.1% 라도 그날은
    비교 가능하다 — 물량이 적으면 **노이즈**가 커질 뿐 **편향**이 생기지는 않는다.
    날짜가 어긋나는 것만이 편향이고, 그래서 그것만 막는다. 임계치로 물량을 거르면
    자의적인 선을 긋는 대신 유효한 비교를 죽이게 된다(체류 커버리지에서 임계치를
    쓰지 않기로 한 것과 같은 이유).
    """
    da, db = _dates_of(cube, axis, a), _dates_of(cube, axis, b)
    for value, dates in ((a, da), (b, db)):
        if not dates:
            raise ConfoundedComparisonError(
                f"{axis}={value!r} does not appear in this cube at all"
            )
    both = sorted(da & db)
    if not both:
        raise ConfoundedComparisonError(
            f"no overlapping dates between {axis}={a!r} ({min(da)}~{max(da)}) and "
            f"{axis}={b!r} ({min(db)}~{max(db)}); a delta across disjoint windows "
            "measures the calendar, not the segment — staged rollouts make this the "
            "normal case for app versions"
        )
    return both


def restrict_to_comparable(
    cube: pd.DataFrame, axis: str, a: str, b: str
) -> pd.DataFrame:
    """두 값과 겹치는 날짜만 남긴 프레임. 이걸 비교의 입력으로 쓴다."""
    dates = comparable_dates(cube, axis, a, b)
    return cube[cube["period"].isin(dates) & cube[axis].isin([a, b])]
