"""결과에 항상 동봉하는 커버리지. 파일시스템도 config 도 모르는 순수 모듈.

스펙은 모든 결과에 커버리지·성연령 매칭률을 붙이라고 요구하는데, `Envelope.coverage`
는 지금까지 호출자가 직접 채워야 하는 빈 dict 였다. 계산을 여기 모아 소비자마다 다르게
재지 않게 한다.

세 가지 모두 **"이 숫자가 전수의 몇 %를 덮는가"** 를 답한다. 커버리지 없이 낸 비율은
전수처럼 읽히고, 축마다 크게 달라서(체류는 `search` 0% ~ `media` 107%) 그 오독이
비교를 조용히 망친다.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from analytics.metrics.frame import full_combination_rows
from analytics.metrics.markov import EXIT, START

_UNKNOWN = "unknown"


def _share(part: float, whole: float) -> float:
    return float(part / whole) if whole > 0 else float("nan")


def demography_coverage(sessions: pd.DataFrame) -> dict[str, float]:
    """성·연령이 실제로 붙은 세션 비율.

    `age_band='unknown'` 은 성연령 테이블 매칭 실패와 원천 센티널(`service_age_band=0`,
    "연령 미상")을 **한 버킷으로 접은 것**이다. 둘을 나누면 축이 9개 값이 되고
    `unknown` 으로 필터하는 소비자가 미상 유저 대부분을 놓친다.

    롤업 행을 제외하고 센다 — 넣으면 같은 세션을 여러 번 세어 비율이 틀어진다.
    """
    axes = ("period", "service_type", "os", "gender", "age_band", "daypart",
            "app_version")
    rows = full_combination_rows(sessions, axes)
    total = float(rows["sessions"].sum())
    return {
        "gender_known": _share(
            float(rows.loc[rows["gender"] != _UNKNOWN, "sessions"].sum()), total
        ),
        "age_band_known": _share(
            float(rows.loc[rows["age_band"] != _UNKNOWN, "sessions"].sum()), total
        ),
    }


def dwell_coverage(edges: pd.DataFrame) -> float:
    """체류가 측정된 화면 방문의 비율 (`dur_n / cnt`).

    `START` 와 `EXIT` 는 화면이 아니라 체류가 있을 수 없다. 분모에 넣으면 커버리지가
    실제보다 낮게 보인다 — `START` 엣지 수는 세션 수와 같아서 왜곡이 크다.
    """
    screens = edges[~edges["from_state"].isin((START, EXIT))]
    return _share(float(screens["dur_n"].sum()), float(screens["cnt"].sum()))


def screen_coverage(quality: pd.DataFrame) -> float:
    """화면 이벤트가 하나 이상인 세션 비율 — 여정 분석의 모집단이다.

    실측 78.0%(설계 시 추정은 53.3% 였다). 서비스 편차가 크다: `top` 은 25.5% 가
    화면 없는 세션이고 다른 서비스는 1.2~7.1% 다.
    """
    rows = quality[quality["check_name"] == "session_no_screen"]
    if rows.empty:
        raise KeyError(
            "session_no_screen is absent from this quality frame; screen coverage "
            "cannot be derived without it"
        )
    violated = float(rows["violated"].sum())
    total = float(rows["total"].sum())
    return float(np.nan) if total <= 0 else 1.0 - violated / total
