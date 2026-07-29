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

# 임계치를 재는 수준. 버전은 접고 **서비스와 날짜는 남긴다.**
WARNING_LEVEL = ("check_name", "service_code", "period")


def _warnings(quality: pd.DataFrame, limits: dict[str, float]) -> list[dict]:
    """`WARNING_LEVEL` 로 집계한 뒤 임계치를 댄다. 나쁜 순으로 낸다."""
    level = [c for c in WARNING_LEVEL if c in quality.columns]
    folded = quality.groupby(level, as_index=False)[["violated", "total"]].sum()
    # 정렬은 안정적이다 — 비율이 같으면 groupby 의 키 순서를 지키므로 재현된다.
    return sorted(quality_warnings(folded, limits), key=lambda w: -w["ratio"])


@analysis("quality_report")
def quality_report(cubes: CubeSet, thresholds: dict[str, float] | None = None,
                   **_) -> AnalysisResult:
    """검사별·날짜별 위반 비율과 임계치 경고.

    **비율은 저장하지 않고 유도한다.** 서비스별 행을 합칠 때 비율을 평균하면 분모가
    사라진다 — 실측 형태로 255/1000 과 12/4000 을 평균하면 12.9% 지만 옳은 값은
    267/5000 = 5.3% 다. 카운트를 합치고 나서 나눈다.

    `thresholds` 를 주지 않으면 shipped config 를 쓴다. 임계치가 없는 검사는 표에는
    나오지만 경고하지 않는다 — 측정된 기저 없이 임계치를 발명하지 않는다.

    **임계치는 버전을 접은 (검사, 서비스, 날짜) 비율에 댄다.** 임계치의 근거가 집계된
    비율(실측 전체 22.0%, `top` 25.5%, 체류 커버리지 57~69%)이므로 같은 수준에서 재야
    범주가 맞는다. 세션 3건짜리 버전의 100% 를 그 임계치에 대면 실측에서 경고가
    18,973건 · 봉투 2.3 MB 가 되고 전부 롱테일이었다. 접으면 18건이고 전부 수천만
    세션이 뒷받침한다 — `search` 의 체류 15일 내내 100%, `top` 의 나쁜 3일 32~38%.

    **서비스는 접지 않는다.** 한 서비스만 나쁜 경우가 평균에 묻히는 것이 이 검사들의
    존재 이유다(실측 `top` 25.5% 대 나머지 1.2~7.1%, 전체로 합치면 22.0% 라 안 걸린다).

    맞바꿈: 버전을 접으면 **한 버전만 망가진 경우가 그 서비스의 일별 숫자에 희석된다.**
    최소 물량 임계치를 발명하는 대신 이쪽을 택했다 — `app_version` 은 축이므로 버전
    질문은 `cubes.filter(app_version=...)` 로 따로 묻는 종류다.
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
        envelope=envelope_for(cubes, coverage, _warnings(quality, limits)),
        viz={"kind": "line", "x": "period"},
    )
