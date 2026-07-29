"""기술통계 분석. `metrics/` 의 프리미티브를 묶어 이름 붙인다."""
from __future__ import annotations

import pandas as pd

from analytics.analyses.base import AnalysisResult, CubeSet, analysis, envelope_for
from analytics.metrics.calendar import day_kind
from analytics.metrics.coverage import demography_coverage
from analytics.metrics.descriptive import SESSION_AXES, engagement, uv_pv
from analytics.metrics.frame import rollup_rows


@analysis("session_trend")
def session_trend(cubes: CubeSet, holidays: set[str] | None = None,
                  **_) -> AnalysisResult:
    """기간별 UV·PV·세션·체류.

    `uv` 는 큐브의 롤업 행에서 읽는다 — 합산하면 실측 1.71배로 부푼다. 그래서 기간 전체
    `uv` 는 `headline` 에 없다: 날짜를 접은 롤업 행이 따로 필요한데 이 분석은 날짜별로
    읽기 때문이다. 세션·PV·체류는 가산이라 합산해도 된다.

    `holidays` 를 주면 요일 종류를 붙인다. **주지 않으면 붙이지 않는다** — 공휴일을
    모르면서 평일로 적으면 평균이 끌려간다(실측 584.2초 vs 602.8초).
    """
    folded = tuple(a for a in SESSION_AXES if a != "period")
    rows = []
    for day in sorted(set(cubes.session["period"].dropna())):
        one = cubes.session[cubes.session["period"] == day]
        base = uv_pv(one, folded=folded).iloc[0]
        eng = engagement(one, folded=folded).iloc[0]
        row = {
            "period": day,
            "sessions": int(base["sessions"]), "uv": int(base["uv"]),
            "pv": int(base["pv"]), "events": int(base["events"]),
            # 비율의 분자를 함께 낸다 — 없으면 소비자가 headline 을 검산할 수 없다.
            # 같은 롤업 행에서 읽는다: `engagement` 의 분모와 어긋나지 않게.
            "duration_sum": int(
                rollup_rows(one, SESSION_AXES, folded=folded)["duration_sum"].iloc[0]
            ),
            "sessions_per_user": eng["sessions_per_user"],
            "pv_per_session": eng["pv_per_session"],
            "seconds_per_session": eng["seconds_per_session"],
            "dwell_definition": eng["dwell_definition"],
        }
        if holidays is not None:
            row["day_kind"] = day_kind(day, holidays)
        rows.append(row)
    frame = pd.DataFrame(rows)

    # headline 은 **기간 전체**의 값이다. 날짜별 값의 평균이 아니다 — 한 headline 안에서
    # 추정량이 섞이면 `decompose` 의 `between` 이 구성 변화가 아니라 추정량 차이를 담는다.
    total_sessions = float(frame["sessions"].sum())
    headline = {
        "sessions": total_sessions,
        "pv_per_session": float(frame["pv"].sum() / total_sessions)
        if total_sessions else float("nan"),
        "seconds_per_session": float(frame["duration_sum"].sum() / total_sessions)
        if total_sessions else float("nan"),
    }
    return AnalysisResult(
        frame=frame, headline=headline, compare_key="period",
        envelope=envelope_for(cubes, demography_coverage(cubes.session)),
        viz={"kind": "line", "x": "period"},
    )
