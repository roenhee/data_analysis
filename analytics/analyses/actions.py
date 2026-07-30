"""행동층 분석. `action` 큐브를 읽어 화면 안의 클릭 분포를 낸다.

`metrics/actions.py` 의 프리미티브를 이름 붙인 분석으로 묶는다. 그래야 발행된다 —
이 층의 규칙이고, 노트북에서 손으로 계산한 값이 결론이 되는 경로를 막는 장치다.
"""
from __future__ import annotations

import numpy as np
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


# 클릭이 하나도 없이 넘어간 전이의 라벨. `analytics/cube/sql.py` 의 `NO_CLICK` 과 같은 값이다.
NO_CLICK = "(no_click)"


def _conditional_information(rows: pd.DataFrame) -> float:
    """I(다음 화면 ; 행동 | 현재 화면) — 단위 nats.

    "현재 화면을 아는 상태에서, **행동을 더 알면** 다음 화면을 얼마나 더 아는가" 다.
    `H(다음|현재) − H(다음|현재, 행동)` 를 현재 화면의 물량으로 가중해 합한다.

    **가중이 두 겹이고 둘 다 물량이다.** 화면끼리 단순 평균하면 전이 2건짜리 화면이 1억 건
    짜리와 같은 무게를 갖고, 한 화면 안에서 행동끼리 단순 평균하면 **음수가 나올 수 있다**
    (실제로 90:10 픽스처에서 0.129 대신 −0.148 이 된다). 조건부 상호정보량은 정의상
    음수가 될 수 없으므로, 음수가 나오면 가중이 틀린 것이다.
    """
    def entropy(counts: pd.Series) -> float:
        total = float(counts.sum())
        if total <= 0:
            return 0.0
        p = counts.to_numpy(dtype=float) / total
        p = p[p > 0]
        return float(-(p * np.log(p)).sum())

    grand = float(rows["cnt"].sum())
    if grand <= 0:
        return float("nan")

    out = 0.0
    for _, per_screen in rows.groupby("from_state", observed=True):
        weight = float(per_screen["cnt"].sum()) / grand
        marginal = entropy(per_screen.groupby("to_state", observed=True)["cnt"].sum())
        within = 0.0
        screen_total = float(per_screen["cnt"].sum())
        for _, per_kind in per_screen.groupby("action_kind", observed=True):
            kind_weight = float(per_kind["cnt"].sum()) / screen_total
            within += kind_weight * entropy(
                per_kind.groupby("to_state", observed=True)["cnt"].sum()
            )
        out += weight * (marginal - within)
    return out


@analysis("conditional_flow")
def conditional_flow(cubes: CubeSet, **_) -> AnalysisResult:
    """어떤 행동이 다음 화면을 결정하는가. (현재 화면, 행동, 다음 화면) 별 건수와 비중.

    `share_of_origin` 의 분모는 **(현재 화면, 행동)** 이다 — "이 화면에서 이걸 눌렀을 때
    어디로 가나". `cnt` 를 전이 수로 읽으면 안 된다: 한 방문에서 클릭이 k번이면 그 전이가
    k행으로 나온다(`analytics/cube/sql.py::build_cond_transition_cube_sql`).

    `headline` 의 `action_information` 은 I(다음 화면 ; 행동 | 현재 화면) 이다(nats).
    "현재 화면을 아는 상태에서 행동을 더 알면 다음 화면을 얼마나 더 아는가" 이고, 0 이면
    행동이 아무것도 말해주지 않는다. `screen_pair_affinity` 의 상호정보량이 I(현재; 다음)
    인 것과 구분된다 — 이쪽은 **현재 화면을 이미 안 다음**의 증분이다.

    **`(no_click)` 은 그 계산에서 뺀다.** 행동이 아니라 "행동이 없었다" 는 사실이라,
    행동 종류로 세면 "안 누름" 이 정보를 준 것처럼 된다. 대신 프레임에는 남기고
    `no_click_share` 로 따로 낸다 — 빼면 "행동이 다음 화면을 결정한다" 가 행동 있는
    전이만 본 결과가 된다.

    `no_click_share` 의 분모는 **전이 큐브의 전이 수**다. 이 큐브의 `cnt` 합은 (클릭, 전이)
    쌍이라 전이 수가 아니다(실측 3억 4,877만 대 3억 371만). 전이 큐브가 없으면 `NaN` 이다.
    """
    rows = cubes.cond_transition
    if rows is None:
        raise ValueError(
            "conditional_flow needs the cond_transition cube; it is absent"
        )

    frame = rows.groupby(
        ["from_state", "action_kind", "to_state"], as_index=False, observed=True
    )["cnt"].sum()
    origin = frame.groupby(["from_state", "action_kind"])["cnt"].transform("sum")
    frame["share_of_origin"] = frame["cnt"] / origin
    frame = frame.sort_values("cnt", ascending=False, ignore_index=True)

    acted = frame[frame["action_kind"] != NO_CLICK]
    no_click = float(frame.loc[frame["action_kind"] == NO_CLICK, "cnt"].sum())

    transitions = float("nan")
    edges = cubes.transition
    if edges is not None and not edges.empty:
        transitions = float(edges["cnt"].sum())

    return AnalysisResult(
        frame=frame,
        headline={
            "action_information": _conditional_information(acted)
            if not acted.empty else float("nan"),
            "no_click_share": no_click / transitions
            if transitions and transitions > 0 else float("nan"),
        },
        compare_key="from_state",
        envelope=envelope_for(cubes, {}),
        viz={"kind": "heatmap", "x": "from_state"},
    )
