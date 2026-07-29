"""분석에 거는 연산자. 가드가 모이는 곳이다.

**비교는 분석 종류가 아니라 분석에 거는 연산이다.** 그래서 가드를 여기 한 번만 두면
분석 전부가 자동으로 보호된다. 분석마다 따로 넣으면 반드시 하나를 빠뜨린다.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from analytics.analyses.base import AnalysisResult, CubeSet, get_analysis
from analytics.metrics.compare import comparable_dates, weight_skew


@dataclass(frozen=True)
class Comparison:
    """두 세그먼트 비교의 산출물.

    **합산 델타만 보면 안 된다.** 실측(2026-07-26~28, MA)에서 날짜별로는
    +6.4/+4.0/+6.3% 인데 합산은 −2.1% 였다 — 부호가 뒤집힌다. 9.5.0 은 07-26 에,
    9.5.1 은 07-28 에 몰려 있어 각 버전이 자기가 몰린 날의 기저 수준을 물고 오기
    때문이다. 같은 버전 하나만 놓고 봐도 날짜만 바뀌면 기대 걸음 수가 11.53~13.23 으로
    15% 움직이는데, 이는 재려는 버전 델타(4~6%)보다 크다.

    `per_day` 와 `sign_disagrees` 가 그걸 즉시 드러낸다.
    """

    pooled: dict[str, float]
    per_day: pd.DataFrame
    weight_skew: float
    dates_used: list[str]
    date_reason: str
    sign_disagrees: bool
    result: AnalysisResult
    # `decompose` 가 같은 분석을 층별로 다시 돌리려면 이름이 필요하다.
    analysis_name: str


def _delta(a: dict[str, float], b: dict[str, float]) -> dict[str, float]:
    out: dict[str, float] = {}
    for key in a.keys() & b.keys():
        denom = b[key]
        out[key] = (a[key] / denom - 1.0) if denom else float("nan")
    return out


def _primary_cube(cubes: CubeSet) -> pd.DataFrame:
    """비교의 날짜·물량을 세는 기준 큐브."""
    if cubes.transition is not None:
        return cubes.transition
    if cubes.session is not None:
        return cubes.session
    raise ValueError("no cube to compare on: both transition and session are absent")


def compare(
    cubes: CubeSet,
    analysis_name: str,
    on: str,
    a: str,
    b: str,
    released: dict[str, str] | None = None,
    **params,
) -> Comparison:
    """`on` 축의 두 값을 비교한다. 어느 분석에나 걸린다.

    가드:

    - **날짜 겹침 강제** — 안 겹치면 버전이 아니라 달력을 잰다(실측 +2.9% vs −0.2%).
    - **배포일 이전 제외** — 배포 전은 테스터, 다른 모집단이다(실측 +2.7% vs −0.4%).
      배포 전 이틀의 전이는 4건·308건이었고 하루 델타가 −79.1% 까지 튀었다.
    - **날짜별 델타를 항상 함께 낸다** — 심슨의 역설을 드러낸다. 임계치로 막지 않고
      보여준다. 4건짜리 날의 −79.1% 는 표를 보면 즉시 쓰레기라는 게 보인다.
    """
    fn = get_analysis(analysis_name)
    cube = _primary_cube(cubes)
    days = comparable_dates(cube, on, a, b, released=released)
    reason = "overlap of both segments"
    if released and any(released.get(v) for v in (a, b)):
        reason += ", after the release cutoff"

    scoped = cubes.filter(dates=days)
    pooled = _delta(fn(scoped.filter(**{on: a}), **params).headline,
                    fn(scoped.filter(**{on: b}), **params).headline)

    rows = []
    for day in days:
        one = scoped.filter(dates=[day])
        d = _delta(fn(one.filter(**{on: a}), **params).headline,
                   fn(one.filter(**{on: b}), **params).headline)
        rows.append({"period": day, **{f"delta_{k}": v for k, v in d.items()}})
    per_day = pd.DataFrame(rows)

    disagrees = False
    for key, pooled_value in pooled.items():
        col = per_day.get(f"delta_{key}")
        if col is None:
            continue
        signs = set(np.sign(col.dropna()))
        if len(signs) == 1 and np.sign(pooled_value) not in signs:
            disagrees = True

    envelope = {
        **fn(scoped.filter(**{on: a}), **params).envelope,
        "present_dates": days,
        "comparison": {"on": on, "a": a, "b": b},
    }
    return Comparison(
        pooled=pooled,
        per_day=per_day,
        weight_skew=weight_skew(cube, on, a, b, released=released),
        dates_used=days,
        date_reason=reason,
        sign_disagrees=disagrees,
        result=AnalysisResult(frame=per_day, headline=pooled, envelope=envelope),
        analysis_name=analysis_name,
    )
