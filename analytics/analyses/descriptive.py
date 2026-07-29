"""기술통계 분석. `metrics/` 의 프리미티브를 묶어 이름 붙인다."""
from __future__ import annotations

import numpy as np
import pandas as pd

from analytics.analyses.base import AnalysisResult, CubeSet, analysis, envelope_for
from analytics.metrics.calendar import day_kind
from analytics.metrics.coverage import demography_coverage, dwell_coverage
from analytics.metrics.descriptive import (
    DWELL_DEFINITION,
    SESSION_AXES,
    engagement,
    screen_dwell,
    uv_pv,
)
from analytics.metrics.frame import full_combination_rows, rollup_rows


def _day_measures(one: pd.DataFrame, folded: tuple[str, ...]) -> tuple[dict, bool]:
    """하루치 측정값과 "슬라이스라 `uv` 를 못 읽었는가".

    롤업 행이 있으면 그걸 읽는다. 세그먼트로 자른 프레임에는 없으므로(롤업 행은 접힌
    축이 NULL 이라 값으로 필터하면 사라진다) **가산 측정값만 전체 조합 행에서 합하고
    `uv` 는 NaN 이다** — 합하면 실측 1.71배로 부푼다. 전체 조합 행만 합하는 것도
    중요하다: 축 하나를 접은 행이 같은 파일에 있어서 그냥 합하면 두 번 센다.
    """
    rollup = rollup_rows(one, SESSION_AXES, folded=folded)
    if not rollup.empty:
        base = uv_pv(one, folded=folded).iloc[0]
        eng = engagement(one, folded=folded).iloc[0]
        return {
            "sessions": int(base["sessions"]), "uv": float(base["uv"]),
            "pv": int(base["pv"]), "events": int(base["events"]),
            "duration_sum": int(rollup["duration_sum"].iloc[0]),
            "sessions_per_user": float(eng["sessions_per_user"]),
            "pv_per_session": float(eng["pv_per_session"]),
            "seconds_per_session": float(eng["seconds_per_session"]),
        }, False

    full = full_combination_rows(one, SESSION_AXES)
    sessions = float(full["sessions"].sum())
    pv = float(full["pv"].sum())
    duration = float(full["duration_sum"].sum())
    return {
        "sessions": int(sessions), "uv": np.nan,
        "pv": int(pv), "events": int(full["events"].sum()),
        "duration_sum": int(duration),
        # uv 가 없으면 유저당 세션의 분모가 없다. 0 도 아니고 1 도 아니다.
        "sessions_per_user": np.nan,
        "pv_per_session": pv / sessions if sessions else np.nan,
        "seconds_per_session": duration / sessions if sessions else np.nan,
    }, True


@analysis("session_trend")
def session_trend(cubes: CubeSet, holidays: set[str] | None = None,
                  **_) -> AnalysisResult:
    """기간별 UV·PV·세션·체류.

    `uv` 는 큐브의 롤업 행에서 읽는다 — 합산하면 실측 1.71배로 부푼다. 그래서 기간 전체
    `uv` 는 `headline` 에 없다: 날짜를 접은 롤업 행이 따로 필요한데 이 분석은 날짜별로
    읽기 때문이다. 세션·PV·체류는 가산이라 합산해도 된다.

    **세그먼트로 자르면 그 롤업 행이 사라지고(접힌 축이 NULL 이라 값으로 필터하면
    빠진다) `uv` 는 NaN 이다** — 봉투에 `uv_unavailable_for_this_slice` 를 싣는다.
    가산 측정값은 전체 조합 행에서 합해 그대로 낸다. 그래서 `headline` 은 두 경로에서
    모두 성립하고, 세션 큐브 분석도 `compare` 에 걸린다(`_day_measures` 참고).

    `holidays` 를 주면 요일 종류를 붙인다. **주지 않으면 붙이지 않는다** — 공휴일을
    모르면서 평일로 적으면 평균이 끌려간다(실측 584.2초 vs 602.8초).
    """
    folded = tuple(a for a in SESSION_AXES if a != "period")
    rows, sliced = [], False
    for day in sorted(set(cubes.session["period"].dropna())):
        one = cubes.session[cubes.session["period"] == day]
        # 비율의 분자를 함께 낸다 — 없으면 소비자가 headline 을 검산할 수 없다.
        measures, without_uv = _day_measures(one, folded)
        sliced = sliced or without_uv
        row = {"period": day, **measures,
               "dwell_definition": DWELL_DEFINITION}
        if holidays is not None:
            row["day_kind"] = day_kind(day, holidays)
        rows.append(row)
    frame = pd.DataFrame(rows)

    warnings = []
    if sliced:
        warnings.append({
            "check_name": "uv_unavailable_for_this_slice",
            "reason": "the cube has no rollup row for this segment, and uv cannot be "
                      "summed into one — it inflated 1.71x on the real cube",
        })

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
        envelope=envelope_for(cubes, demography_coverage(cubes.session), warnings),
        viz={"kind": "line", "x": "period"},
    )


@analysis("screen_dwell_rank")
def screen_dwell_rank(cubes: CubeSet, warn_below: float = 0.5,
                      **_) -> AnalysisResult:
    """화면별 방문당 체류(초) 순위.

    **분모는 `cnt` 가 아니라 `dur_n` 이다.** 측정되지 않은 방문까지 분모에 넣으면
    커버리지만큼 축소된 값이 나온다 — 실측 6.67초 대 10.0초.

    `headline` 은 측정된 방문으로 가중한다(= 전체 `dur_sum` / 전체 `dur_n`). 화면끼리
    단순 평균하면 방문이 거의 없는 화면이 흔한 화면과 같은 무게를 갖는다.

    커버리지도 `headline` 에 넣는다. 세그먼트끼리 커버리지가 다르면 조건부 평균은
    애초에 비교가 안 되는데, headline 에 있으면 `compare` 가 그 델타를 함께 낸다.

    커버리지가 `warn_below` 미만이면 경고한다. **막지 않는다** — 조건부 평균 자체는
    옳고, 그게 전수를 대표하지 못한다는 사실만 봉투에 실어 보낸다.
    """
    edges = cubes.transition
    if edges is None:
        raise ValueError("screen_dwell_rank needs the transition cube; it is absent")
    frame = screen_dwell(edges).sort_values(
        "seconds_per_visit", ascending=False, ignore_index=True
    )

    # 체류가 측정된 방문이 없는 화면은 분자도 분모도 없다. NaN 을 곱해 넣으면
    # 가중합 전체가 NaN 이 되므로 먼저 뺀다.
    usable = frame.dropna(subset=["seconds_per_visit"])
    measured = float(usable["measured_visits"].sum())
    coverage = dwell_coverage(edges)

    warnings = []
    if coverage < warn_below:
        warnings.append({
            "check_name": "low_dwell_coverage",
            "coverage": float(coverage),
            "threshold": float(warn_below),
        })

    headline = {
        "mean_seconds_per_visit": float(
            (usable["seconds_per_visit"] * usable["measured_visits"]).sum() / measured
        ) if measured > 0 else float("nan"),
        "dwell_coverage": float(coverage),
    }
    return AnalysisResult(
        frame=frame, headline=headline, compare_key="state",
        envelope=envelope_for(cubes, {"dwell": coverage}, warnings),
        viz={"kind": "bar", "x": "state"},
    )
