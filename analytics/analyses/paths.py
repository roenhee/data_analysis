"""경로 분석. `path` 큐브를 읽어 n-gram 순위와 1차 마르코프 가정 검정을 낸다.

**`path` 큐브는 크다** — 실측 하루 136만 행(약 14 MB), 15일이면 2,040만 행 · 215 MB 다.
전이 큐브(15일 328만 행)의 6배이므로, 세그먼트를 먼저 좁혀서 부르는 것이 정상 사용법이다.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from analytics.analyses.base import AnalysisResult, CubeSet, analysis, envelope_for
from analytics.metrics.paths import (
    OTHER_PATH,
    TAIL_DOMINATES_ABOVE,
    _one_n,
    path_coverage,
    top_paths,
)

# 3-gram 문맥 하나에서 1차 예측과의 발산이 이 값을 넘으면 그 문맥은 1차로 설명되지 않는다.
# 전체 지표는 `excess_information` 이고 이건 프레임을 읽는 사람이 쓰는 눈금이다.
CONTEXT_DIVERGES_ABOVE = 0.1


@analysis("path_ranking")
def path_ranking(cubes: CubeSet, n: int, **_) -> AnalysisResult:
    """세션이 밟은 `n` 걸음 경로 순위.

    **`n` 은 필수다.** 기본값을 주면 n=3 과 n=4 를 섞어 부르게 되는데 둘은 **다른 모집단**
    이고(같은 방문이 여러 n 에 등장한다) 합치면 같은 방문이 여러 번 세어진다. 그래서
    `headline` 에도 `n` 을 싣는다 — `compare` 가 headline 델타를 내므로, 두 n 을 비교한
    결과는 `delta_n` 이 0 이 아닌 것으로 드러난다.

    **`(other)` 는 경로가 아니라 컷의 크기다.** 세그먼트×n 마다 상위 200 만 남기고 나머지를
    그 한 행에 접었으므로 순위에서 뺀다 — 실측 n=4 는 90 대 10 으로 1위가 된다. 반대로
    **비중의 분모에서는 빼지 않는다**: 상위 200 안에서만 정규화하면 남은 값이 부푼다.

    `headline` 이 컷의 크기를 함께 낸다. 커버리지 0.1 이 "200개가 꼬리 전부" 인지
    "9,000개를 잘랐" 는지로 해석이 완전히 갈리기 때문이다 — `distinct_dropped` 가 그걸
    가른다. `(other)` 가 절반을 넘으면 봉투에 `path_tail_dominates` 를 싣는다.
    """
    if cubes.path is None:
        raise ValueError("path_ranking needs the path cube; it is absent")

    frame = top_paths(cubes.path, n=n)
    coverage = path_coverage(cubes.path, n=n)

    warnings = []
    if frame.attrs.get("tail_dominates"):
        warnings.append({
            "check_name": "path_tail_dominates",
            "ratio": 1.0 - coverage,
            "threshold": TAIL_DOMINATES_ABOVE,
            "reason": f"the top paths cover only {coverage:.1%} of n={n} windows; the "
                      "ranking is not representative of how sessions actually move",
        })

    return AnalysisResult(
        frame=frame,
        headline={
            # `n` 을 headline 에 넣는 이유는 위 docstring 참고 — 섞인 비교를 드러낸다.
            "n": float(n),
            "coverage": coverage,
            "distinct_dropped": float(frame.attrs.get("distinct_dropped", 0)),
            "paths": float(len(frame)),
            "top_path_share": float(frame["share"].iloc[0]) if not frame.empty
            else float("nan"),
        },
        compare_key="path",
        envelope=envelope_for(cubes, {}, warnings),
        viz={"kind": "bar", "x": "path"},
    )


def _parse_trigrams(rows: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    """`a>b>c` 를 `(prev_state, state, next_state)` 로 가른다. 못 가른 행 수도 낸다.

    화면 이름에 `>` 가 들어가면 조각이 3개가 아니다. 실측 사전 10개에는 없지만
    `action.name` 에 `>` 가 있는 값이 원천에 존재하므로(`다음검색>클릭`) 조용히 넘기지
    않고 세어서 봉투에 싣는다.
    """
    kept = rows[rows["path"] != OTHER_PATH]
    parts = kept["path"].str.split(">")
    good = parts.map(len) == 3
    frame = pd.DataFrame({
        "prev_state": [p[0] for p in parts[good]],
        "state": [p[1] for p in parts[good]],
        "next_state": [p[2] for p in parts[good]],
        "cnt": kept.loc[good, "cnt"].to_numpy(dtype=float),
    })
    return frame, int((~good).sum())


@analysis("markov_order_test")
def markov_order_test(cubes: CubeSet, **_) -> AnalysisResult:
    """1차 마르코프 가정이 성립하는가. **직전 화면을 하나 더 알면 예측이 나아지는가.**

    전이 큐브 하나만 보면 이 질문은 검증되지 않는다 — 그 큐브 자체가 "다음 화면은 현재
    화면만으로 정해진다" 는 가정으로 만들어졌기 때문이다. `path` 큐브의 3-gram 이 있어야
    관측 `P(다음 | 직전, 현재)` 를 1차 예측 `P(다음 | 현재)` 와 대조할 수 있다.

    **1차 예측은 전이 큐브에서 가져온다.** 경로 큐브의 자체 marginal 이 아니다 — 검정
    대상이 "이 프로젝트의 마르코프 분석들이 실제로 쓰는 모델" 이어야 뜻이 있다. 그래서
    경로 큐브의 상위 200 컷이 물리면 `excess_information` 이 순수한 상호정보량과 조금
    달라진다(컷이 없으면 둘은 같다).

    `excess_information` 은 문맥별 KL(관측 ‖ 1차 예측)을 **문맥 물량으로 가중**한 합이다
    (nats). 0 이면 직전 화면이 아무것도 더 말해주지 않는다 — 1차로 충분하다는 뜻이다.
    **문맥을 단순 평균하면 안 된다**: 관측 3건짜리 문맥이 1,000건짜리와 같은 무게를 갖고,
    얇은 문맥의 KL 이 가장 크게 튄다(90:10 픽스처에서 0.129 대 0.441).

    중간 화면이 전이 큐브에 없는 문맥은 **건너뛴다** — 1차 예측을 만들 수 없으므로 검정
    대상이 아니고, 0 으로 때우면 "1차가 완벽히 맞는다" 는 없는 사실이 된다.

    `coverage` 를 함께 낸다. 상위 200 컷 때문에 검정은 **남은 경로에 대해서만** 성립한다.
    """
    if cubes.path is None:
        raise ValueError("markov_order_test needs the path cube; it is absent")
    edges = cubes.transition
    if edges is None:
        raise ValueError(
            "markov_order_test needs the transition cube for the first-order "
            "prediction; it is absent"
        )

    grams, unparsed = _parse_trigrams(_one_n(cubes.path, 3))
    # 큐브는 세그먼트(축 조합)별로 쪼개져 있고 전체 rollup 행이 없다 — 같은 3-gram 이
    # os·성별·버전마다 다른 행이다. 관측 분포를 만들기 전에 합치지 않으면 조각 확률이
    # 1차 예측(전이 큐브에서 세그먼트를 합쳐 온다)보다 작아 KL 이 음수가 된다.
    grams = grams.groupby(["prev_state", "state", "next_state"],
                          as_index=False)["cnt"].sum()

    # 1차 예측: `P(다음 | 현재)` — 전이 큐브의 행 정규화.
    pair = edges.groupby(["from_state", "to_state"], observed=True)["cnt"].sum()
    row_total = pair.groupby("from_state").transform("sum")
    predicted = (pair / row_total).rename("p_first_order").reset_index()
    predicted = predicted.rename(
        columns={"from_state": "state", "to_state": "next_state"}
    )

    joined = grams.merge(predicted, on=["state", "next_state"], how="left")
    # 중간 화면이 전이 큐브에 아예 없으면 1차 예측을 만들 수 없어 검정 대상이 아니다.
    joined = joined[joined["state"].isin(set(edges["from_state"]))]

    rows = []
    for (prev, state), group in joined.groupby(["prev_state", "state"],
                                               observed=True):
        total = float(group["cnt"].sum())
        if total <= 0:
            continue
        observed = group["cnt"].to_numpy(dtype=float) / total
        expected = group["p_first_order"].to_numpy(dtype=float)
        usable = (observed > 0) & np.isfinite(expected) & (expected > 0)
        divergence = float(
            (observed[usable] * np.log(observed[usable] / expected[usable])).sum()
        ) if usable.any() else float("nan")
        rows.append({"prev_state": prev, "state": state, "cnt": total,
                     "divergence": divergence})

    frame = pd.DataFrame(
        rows, columns=["prev_state", "state", "cnt", "divergence"]
    ).sort_values("cnt", ascending=False, ignore_index=True)

    weight_total = float(frame["cnt"].sum()) if not frame.empty else 0.0
    usable = frame.dropna(subset=["divergence"])
    excess = float(
        (usable["divergence"] * usable["cnt"]).sum() / weight_total
    ) if weight_total > 0 else float("nan")

    warnings = []
    if unparsed:
        warnings.append({
            "check_name": "unparsable_path",
            "rows": unparsed,
            "reason": "a screen name contains the '>' separator, so the 3-gram could "
                      "not be split into three states; those rows are excluded",
        })

    return AnalysisResult(
        frame=frame,
        headline={
            "excess_information": excess,
            "contexts": float(len(frame)),
            "coverage": path_coverage(cubes.path, n=3),
            "diverging_context_share": float(
                usable.loc[usable["divergence"] > CONTEXT_DIVERGES_ABOVE, "cnt"].sum()
                / weight_total
            ) if weight_total > 0 else float("nan"),
        },
        compare_key="state",
        envelope=envelope_for(cubes, {}, warnings),
        viz={"kind": "bar", "x": "state"},
    )
