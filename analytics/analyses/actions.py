"""행동층 분석. `action` 큐브를 읽어 화면 안의 클릭 분포를 낸다.

`metrics/actions.py` 의 프리미티브를 이름 붙인 분석으로 묶는다. 그래야 발행된다 —
이 층의 규칙이고, 노트북에서 손으로 계산한 값이 결론이 되는 경로를 막는 장치다.
"""
from __future__ import annotations

import pandas as pd

from analytics.analyses.base import AnalysisResult, CubeSet, analysis, envelope_for
from analytics.metrics.actions import click_share
from analytics.metrics.services import NON_SCREEN_STATES

# 화면에 귀속되지 않은 클릭이 이 비중을 넘으면 화면별 분포가 대표성을 잃는다.
# 실측 하루치는 1.61%(274만 / 1억 7,096만)라 걸리지 않는다 — 임계치를 관측값 위에 둬서
# **드리프트 탐지기**로 쓴다(`quality_thresholds.json` 과 같은 규칙).
UNATTRIBUTED_WARN_ABOVE = 0.10


@analysis("click_distribution")
def click_distribution(cubes: CubeSet, by: tuple[str, ...] = ("action_kind",),
                       **_) -> AnalysisResult:
    """화면 안에서 무엇을 누르는가. 화면별 `by` 조합의 클릭 건수와 **화면 안 비중**.

    **전역으로 정규화하지 않는다.** 트래픽이 많은 화면이 분포를 지배해서 작은 화면의 행동
    구성이 지워진다 — 실측에서 top 이 클릭의 66%를 차지한다. 화면 안에서 정규화하면
    "이 화면에 들어온 사람은 무엇을 누르나" 가 되어 화면끼리 견줄 수 있다.

    `by` 로 축을 고른다. 기본은 `action_kind` 이고 `("layer1",)` 이나
    `("layer1", "layer2")` 도 된다 — 슬롯 단위 분포는 다른 질문이다.

    `headline` 의 `clicks_per_visit` 은 **전이 큐브와 조인해서** 낸다. `action` 큐브의
    `screen` 과 `transition` 큐브의 `from_state` 가 같은 식으로 만들어져 있어서 가능하다
    (`measurements/2026-07-30-screen-namespace.md` 의 결정). 전이 큐브가 없으면 `NaN` 이다 —
    0 으로 채우면 "안 누른다" 와 "방문을 모른다" 가 섞인다.

    `unattributed_share` 를 **headline 에 넣는다.** 첫 화면 이전 클릭은 `START` 에 붙는데,
    세그먼트끼리 그 비중이 다르면 화면별 분포 자체가 비교 불가다 — `screen_dwell_rank` 가
    `dwell_coverage` 를 headline 에 넣는 것과 같은 이유다. 실측 하루치 1.61%.
    """
    actions = cubes.action
    if actions is None:
        raise ValueError("click_distribution needs the action cube; it is absent")

    frame = click_share(actions, by=by)
    total = float(actions["cnt"].sum())
    unattributed = float(
        actions.loc[actions["screen"].isin(NON_SCREEN_STATES), "cnt"].sum()
    )
    on_screen = total - unattributed

    visits = float("nan")
    edges = cubes.transition
    if edges is not None and not edges.empty:
        screens_only = edges[~edges["from_state"].isin(NON_SCREEN_STATES)]
        visits = float(screens_only["cnt"].sum())

    warnings = []
    share = unattributed / total if total > 0 else float("nan")
    if total > 0 and share > UNATTRIBUTED_WARN_ABOVE:
        warnings.append({
            "check_name": "clicks_without_a_screen",
            "ratio": share,
            "threshold": UNATTRIBUTED_WARN_ABOVE,
            "reason": "these clicks preceded the session's first Pageview and carry "
                      "no screen; the per-screen distribution excludes them",
        })

    return AnalysisResult(
        frame=frame,
        headline={
            "clicks": total,
            # 분모는 **화면** 방문이라 `START` 엣지를 뺀다. 분자도 화면에 귀속된 클릭이다 —
            # 둘 다 같은 모집단이어야 비율이 뜻을 갖는다.
            "clicks_per_visit": on_screen / visits if visits and visits > 0
            else float("nan"),
            "unattributed_share": share,
        },
        compare_key="screen",
        envelope=envelope_for(cubes, {}, warnings),
        viz={"kind": "bar", "x": "screen"},
    )
