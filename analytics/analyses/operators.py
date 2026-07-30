"""분석에 거는 연산자. 가드가 모이는 곳이다.

**비교는 분석 종류가 아니라 분석에 거는 연산이다.** 그래서 가드를 여기 한 번만 두면
분석 전부가 자동으로 보호된다. 분석마다 따로 넣으면 반드시 하나를 빠뜨린다.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from analytics.analyses.base import AnalysisResult, CubeSet, get_analysis
from analytics.metrics.compare import comparable_dates, weight_skew
from analytics.metrics.descriptive import SESSION_AXES
from analytics.metrics.frame import full_combination_rows
from analytics.metrics.services import NON_SCREEN_STATES, other_share, services_of


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
    # 그리고 **같은 params 로** 돌려야 한다. 기본값으로 다시 돌면 층별 델타가 `pooled`
    # 와 다른 지표를 재고, `between = pooled - within` 이 그 차이를 조용히 삼킨다.
    params: dict = field(default_factory=dict)


def _delta(a: dict[str, float], b: dict[str, float]) -> dict[str, float]:
    out: dict[str, float] = {}
    for key in a.keys() & b.keys():
        denom = b[key]
        out[key] = (a[key] / denom - 1.0) if denom else float("nan")
    return out


def _volume_frame(cubes: CubeSet) -> tuple[pd.DataFrame, str]:
    """날짜·층 가중치를 셀 프레임과 그 컬럼.

    전이 큐브는 `cnt`, 세션 큐브는 `sessions` 다. **세션 큐브는 전체 조합 행만 쓴다** —
    `GROUPING SETS` 롤업 행이 같은 파일에 있어서 그냥 세면 grouping set 수만큼 부푼다.
    비중만 보는 `weight_skew` 는 그 부풀림에 둔감할 수 있지만, `decompose` 가 표에
    싣는 `a_cnt`·`b_cnt` 는 사람이 읽는 절대 물량이라 틀리면 안 된다.
    """
    if cubes.transition is not None:
        frame, measure, which = cubes.transition, "cnt", "transition"
    elif cubes.session is not None:
        frame = full_combination_rows(cubes.session, SESSION_AXES)
        measure, which = "sessions", "session"
    else:
        raise ValueError(
            "no cube to compare on: both transition and session are absent"
        )
    if measure not in frame.columns:
        raise ValueError(
            f"the {which} cube has no {measure!r} column "
            f"(has: {', '.join(map(str, frame.columns))}); weighting by zero would "
            "report the whole delta as composition rather than refusing"
        )
    return frame, measure


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
    cube, measure = _volume_frame(cubes)
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
        weight_skew=weight_skew(cube, on, a, b, measure=measure, released=released),
        dates_used=days,
        date_reason=reason,
        sign_disagrees=disagrees,
        result=AnalysisResult(frame=per_day, headline=pooled, envelope=envelope),
        analysis_name=analysis_name,
        params=dict(params),
    )


@dataclass(frozen=True)
class Decomposition:
    """델타를 **층 안 변화**와 **구성 변화**로 가른다.

    `within` 이 버전 효과 추정치다. `between` 은 "두 세그먼트가 서로 다른 층에 몰려
    있어서 생긴 몫" 이고, 실측에서 이게 부호를 뒤집었다(층별 +4~6%, 합산 −2.1%).
    """

    within: float
    between: float
    per_stratum: pd.DataFrame
    composition: dict[str, float]


def decompose(
    cubes: CubeSet, comparison: Comparison, by: list[str], metric: str
) -> Decomposition:
    """비교를 층으로 갈라 `within` 과 `between` 으로 분해한다.

    `within + between == pooled_delta` 가 항상 성립한다. 안 맞으면 분해가 틀렸다.

    `within` 은 **b 쪽 층 비중으로 가중한** 층별 델타의 합이다(표준 분해). 즉
    "구성이 b 와 같았다면 델타가 얼마였겠나" 이다.

    날짜 겹침·배포일 가드는 다시 걸지 않는다 — `comparison.dates_used` 를 그대로
    물려받는다. 가드는 `compare` 한 곳에만 있다.
    """
    if metric not in comparison.pooled:
        raise KeyError(
            f"{metric!r} is not in the comparison headline; known: "
            f"{', '.join(sorted(comparison.pooled))}"
        )
    on = comparison.result.envelope["comparison"]["on"]
    a = comparison.result.envelope["comparison"]["a"]
    b = comparison.result.envelope["comparison"]["b"]
    fn = get_analysis(comparison.analysis_name)
    cube, measure = _volume_frame(cubes)
    scoped = cubes.filter(dates=comparison.dates_used)

    rows = []
    # 비교 창 밖의 층까지 돌린다 — 한쪽에만 있는 층을 버리지 않고 NaN 으로 보고한다.
    for keys, _ in cube.groupby(by):
        keys = keys if isinstance(keys, tuple) else (keys,)
        sel = dict(zip(by, keys))
        one = scoped.filter(**sel)
        sa, sb = one.filter(**{on: a}), one.filter(**{on: b})
        ca = float(_volume_frame(sa)[0][measure].sum())
        cb = float(_volume_frame(sb)[0][measure].sum())
        if ca <= 0 or cb <= 0:
            rows.append({**sel, "a_cnt": ca, "b_cnt": cb, "delta": np.nan})
            continue
        d = _delta(fn(sa, **comparison.params).headline,
                   fn(sb, **comparison.params).headline).get(metric, np.nan)
        rows.append({**sel, "a_cnt": ca, "b_cnt": cb, "delta": d})
    per = pd.DataFrame(rows)

    usable = per.dropna(subset=["delta"])
    total_b = usable["b_cnt"].sum()
    wb = usable["b_cnt"] / total_b if total_b > 0 else 0
    within = float((usable["delta"] * wb).sum())
    between = float(comparison.pooled[metric] - within)

    composition = {}
    for axis in by:
        ga = per.groupby(axis)["a_cnt"].sum()
        gb = per.groupby(axis)["b_cnt"].sum()
        pa = ga / ga.sum() if ga.sum() > 0 else ga
        pb = gb / gb.sum() if gb.sum() > 0 else gb
        composition[axis] = float((pa - pb).abs().sum() / 2)

    return Decomposition(within=within, between=between, per_stratum=per,
                         composition=composition)


@dataclass(frozen=True)
class ServiceBreakdown:
    """같은 분석을 서비스별로 돌린 결과.

    `outside_range` 가 이 연산자의 존재 이유다. 서비스는 축이 아니라 빌드 범위라(세션
    44.7%가 여러 서비스에 걸친다) 분석이 합산값 하나를 내는데, **그 값이 서비스별 값의
    범위 밖일 수 있다.** 실측 15일에서 `mean_expected_steps` 합산 10.62 는 최대값
    8.08 보다도 크다 — 화면 간 전이의 49.68%가 서비스를 건너뛰어서, 합친 체인에는 어떤
    단일 서비스 안에도 없는 전이가 들어 있기 때문이다.

    `cross_service_share` 는 서비스별로 자를 때 **사라진** 전이 비중이다. 안 내면
    "서비스별로 다 봤다" 고 읽힌다.
    """

    frame: pd.DataFrame
    pooled: dict[str, float]
    outside_range: dict[str, tuple[float, float]]
    cross_service_share: float
    services: list[str]


def _service_slice(
    cubes: CubeSet, service: str, from_svc: pd.Series, to_svc: pd.Series
) -> CubeSet:
    """그 서비스 안에서만 일어난 전이. 세션 경계(`START`·`EXIT`)는 남긴다.

    `from_svc`·`to_svc` 를 **밖에서 받는다.** 여기서 다시 계산하면 서비스마다 328만 행을
    두 번 훑어 실측 5.5초가 되는데, 부르는 쪽이 이미 갖고 있는 값이다.
    """
    edges = cubes.transition

    def belongs(column, service_column):
        # `fillna(False)` 가 없으면 서비스가 없는 상태에서 비교가 `NA` 가 되고, `NA` 가
        # 섞인 불리언으로 인덱싱하면 pandas 가 거부한다.
        same = service_column.eq(service).fillna(False)
        return same | edges[column].isin(NON_SCREEN_STATES)

    quality = cubes.quality
    return CubeSet(
        session=None,
        transition=edges[
            belongs("from_state", from_svc) & belongs("to_state", to_svc)
        ],
        quality=quality[quality["service_code"] == service]
        if quality is not None and "service_code" in quality.columns
        else None,
        state_dict_version=cubes.state_dict_version, services=[service],
        requested_dates=list(cubes.requested_dates),
        present_dates=list(cubes.present_dates),
    )


def per_service(cubes: CubeSet, analysis_name: str, **params) -> ServiceBreakdown:
    """`analysis_name` 을 서비스별로 돌린다. 어느 분석에나 걸린다.

    서비스는 화면 이름 접두어에서 읽는다 — 큐브를 다시 만들지 않는다(`metrics/services.py`).
    한 서비스에서 분석이 죽으면 그 행을 NaN 으로 낸다. 조용히 빼면 표가 전수처럼 읽힌다.
    """
    fn = get_analysis(analysis_name)
    if cubes.transition is None:
        raise ValueError(
            f"{analysis_name!r} runs on a cube that cannot be split by service: the "
            "session cube has no service column and 44.7% of sessions span more than "
            "one service, so splitting them would double-count"
        )
    # 프레임을 복사하지 않는다 — 실측 328만 행이다. 서비스는 시리즈로만 들고 있는다.
    edges = cubes.transition
    from_svc = services_of(edges["from_state"])
    to_svc = services_of(edges["to_state"])
    counts = edges["cnt"]

    # **분모가 둘이다. 섞으면 물량이 조용히 틀린다.**
    #  - `share`/`cnt` 는 화면에서 **출발한** 전이 기준 (`-> EXIT` 포함). 방문 가중 지표가
    #    무엇으로 구성됐는지 말하는 값이라 화면 출발이 맞는 분모다.
    #  - `cross_service_share` 는 화면에서 **화면으로** 간 전이 기준. 서비스를 건너뛰는지
    #    물으려면 도착도 화면이어야 한다.
    originating = from_svc.notna()
    by_service = counts[originating].groupby(from_svc[originating]).sum()
    origin_total = float(by_service.sum())

    both = originating & to_svc.notna()
    s2s_total = float(counts[both].sum())
    crossing = float(counts[both & (from_svc != to_svc)].sum())

    pooled = fn(cubes, **params).headline
    # 지표 옆에 사전 커버리지를 함께 싣는다 — `/other` 가 큰 서비스의 값은 접힌 상태
    # 때문에 치우쳐 있고, 열이 떨어져 있으면 소비자가 짝지어 읽지 않는다.
    lumped = other_share(edges)
    rows = []
    for service in sorted(by_service.index):
        volume = float(by_service[service])
        row = {"service": service, "cnt": volume,
               "share": volume / origin_total if origin_total else float("nan"),
               "other_share": lumped.get(service, 0.0)}
        try:
            row.update(
                fn(_service_slice(cubes, service, from_svc, to_svc),
                   **params).headline
            )
        except Exception as exc:  # 한 서비스가 죽어도 나머지는 낸다
            row["error"] = f"{type(exc).__name__}: {exc}"
        rows.append(row)
    frame = pd.DataFrame(rows)

    outside = {}
    for key, value in pooled.items():
        if key not in frame.columns:
            continue
        column = frame[key].dropna()
        if column.empty:
            continue
        lo, hi = float(column.min()), float(column.max())
        if value < lo or value > hi:
            outside[key] = (lo, hi)

    return ServiceBreakdown(
        frame=frame, pooled=pooled, outside_range=outside,
        cross_service_share=crossing / s2s_total if s2s_total else float("nan"),
        services=sorted(by_service.index),
    )
