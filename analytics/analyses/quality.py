"""품질 검사 분석. `metrics/envelope.py` 의 경고 규칙을 이름 붙여 감싼다."""
from __future__ import annotations

import numpy as np
import pandas as pd

from analytics.analyses.base import (
    AnalysisResult,
    CubeSet,
    analysis,
    envelope_for,
)
from analytics.metrics.coverage import screen_coverage
from analytics.metrics.envelope import quality_warnings
from analytics.metrics.load import load_quality_thresholds

# 이탈 정의를 뒷받침하는 검사. 위반율이 아니라 **뒷받침율**로 뒤집어 낸다.
EXIT_CHECK = "exit_without_appexit"


@analysis("quality_report")
def quality_report(cubes: CubeSet, thresholds: dict[str, float] | None = None,
                   **_) -> AnalysisResult:
    """검사별·날짜별 위반 비율과 임계치 경고.

    **비율은 저장하지 않고 유도한다.** 서비스별 행을 합칠 때 비율을 평균하면 분모가
    사라진다 — 실측 형태로 255/1000 과 12/4000 을 평균하면 12.9% 지만 옳은 값은
    267/5000 = 5.3% 다. 카운트를 합치고 나서 나눈다.

    `thresholds` 를 주지 않으면 shipped config 를 쓴다. 임계치가 없는 검사는 표에는
    나오지만 경고하지 않는다 — 측정된 기저 없이 임계치를 발명하지 않는다.

    경고는 **원본 행 단위**(서비스·버전·날짜)로 낸다. 합쳐 놓으면 한 서비스만 나쁜
    경우가 평균에 묻힌다 — 실측에서 `top` 은 25.5% 인데 나머지는 1.2~7.1% 였다.
    """
    quality = cubes.quality
    if quality is None:
        raise ValueError("quality_report needs the quality cube; it is absent")
    limits = load_quality_thresholds() if thresholds is None else thresholds

    frame = (
        quality.groupby(["check_name", "period"], as_index=False)[
            ["violated", "total"]
        ].sum().sort_values(["check_name", "period"], ignore_index=True)
    )
    # 분모가 0 이면 NaN 이다 — 0% 위반과 "잰 것이 없다" 는 다른 말이다.
    frame["ratio"] = np.where(
        frame["total"] > 0, frame["violated"] / frame["total"], np.nan
    )

    headline = {
        f"worst_{name}": float(group["ratio"].max())
        for name, group in frame.groupby("check_name")
    }
    exits = frame[frame["check_name"] == EXIT_CHECK]
    exit_total = float(exits["total"].sum())
    if exit_total > 0:
        # 뒷받침 정도 = 1 - 위반율. 실측 89.2%. 위반율로 내면 "높을수록 좋다" 와
        # "낮을수록 좋다" 가 한 headline 안에 섞인다.
        headline["exit_corroboration"] = 1.0 - float(
            exits["violated"].sum()
        ) / exit_total

    coverage = {}
    try:
        coverage["screen"] = screen_coverage(quality)
    except KeyError:
        # `session_no_screen` 이 없는 품질 프레임도 있다. 없으면 넣지 않는다 —
        # 0 으로 채우면 "화면 있는 세션이 하나도 없다" 가 된다.
        pass

    return AnalysisResult(
        frame=frame, headline=headline, compare_key="check_name",
        envelope=envelope_for(cubes, coverage, quality_warnings(quality, limits)),
        viz={"kind": "line", "x": "period"},
    )
