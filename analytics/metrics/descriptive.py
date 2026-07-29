"""기술통계. 큐브 프레임만 받는 순수 함수다.

**`uv` 는 절대 합산하지 않는다.** 롤업은 큐브가 `GROUPING SETS` 로 미리 만들어 두었고,
없는 조합을 요청하면 합산으로 때우지 않고 거부한다. 같은 유저가 이틀 방문하면 1이지
2가 아니다 — 실측 큐브에서 합산하면 1.71배 부푼다.

체류가 **두 가지**이고 정의가 다르다는 점에 주의한다:

- `session` 큐브의 `duration_sum`: 세션 span(`date_diff` 초), 커버리지 100%
- `transition` 큐브의 `dur_sum`: `UsagePage` 기반, 커버리지 57~69%

두 값을 같은 이름으로 부르면 섞인다. 결과 프레임에 `dwell_definition` 을 붙여 낸다.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from analytics.metrics.frame import NonAdditiveMeasureError, rollup_rows
from analytics.metrics.markov import EXIT, START

SESSION_AXES = (
    "period", "service_type", "os", "gender", "age_band", "daypart", "app_version",
)

# 세션 큐브의 체류는 세션 span(첫→마지막 이벤트, 초)이라 커버리지가 100% 다.
DWELL_DEFINITION = "session_span_seconds"

# 전이 큐브의 체류는 `UsagePage` 행에서 오고 커버리지가 축마다 다르다(실측 57~69%).
TRANSITION_DWELL_DEFINITION = "usagepage_seconds"


def _rows(cube: pd.DataFrame, folded: tuple[str, ...]) -> pd.DataFrame:
    rows = rollup_rows(cube, SESSION_AXES, folded=folded)
    if rows.empty and folded:
        raise NonAdditiveMeasureError(
            f"the cube has no rollup row with {list(folded)} folded, and uv cannot be "
            "summed to make one; rebuild the cube with that grouping set"
        )
    return rows


def _ratio(numerator: pd.Series, denominator: pd.Series) -> np.ndarray:
    return np.where(denominator > 0, numerator / denominator, np.nan)


def uv_pv(cube: pd.DataFrame, folded: tuple[str, ...] = ()) -> pd.DataFrame:
    """UV·PV·세션·이벤트. `folded` 축은 큐브의 롤업 행에서 읽는다."""
    rows = _rows(cube, folded)
    keep = [a for a in SESSION_AXES if a not in folded]
    return rows[keep + ["sessions", "uv", "pv", "events"]].reset_index(drop=True)


def engagement(cube: pd.DataFrame, folded: tuple[str, ...] = ()) -> pd.DataFrame:
    """유저당 세션, 세션당 PV, 세션당 체류(초).

    체류는 세션 span 이라 커버리지가 100% 다 — 전이 큐브의 `screen_dwell` 과 다른
    정의이므로 `dwell_definition` 을 함께 낸다.
    """
    rows = _rows(cube, folded)
    keep = [a for a in SESSION_AXES if a not in folded]
    out = rows[keep].copy().reset_index(drop=True)
    out["sessions_per_user"] = _ratio(rows["sessions"], rows["uv"])
    out["pv_per_session"] = _ratio(rows["pv"], rows["sessions"])
    out["seconds_per_session"] = _ratio(rows["duration_sum"], rows["sessions"])
    out["dwell_definition"] = DWELL_DEFINITION
    return out


def screen_dwell(edges: pd.DataFrame) -> pd.DataFrame:
    """화면별 방문당 체류(초)와 그 커버리지.

    **분모는 `cnt` 가 아니라 `dur_n` 이다.** `dur_sum / cnt` 는 체류가 측정되지 않은
    방문까지 분모에 넣어 커버리지만큼 축소된 값을 낸다. 옳은 값은 "체류가 측정된
    방문"에 대한 조건부 평균이고, `dur_n / cnt` 가 그 커버리지다.

    측정된 방문이 하나도 없으면 `NaN` 이다 — 0 으로 내면 "0초 머물렀다"와
    "얼마나 머물렀는지 모른다"가 구분되지 않는다.
    """
    grouped = (
        edges.groupby("from_state", as_index=False)[["cnt", "dur_sum", "dur_n"]].sum()
    )
    grouped = grouped[~grouped["from_state"].isin((START, EXIT))]
    out = pd.DataFrame({"state": grouped["from_state"].to_numpy()})
    out["visits"] = grouped["cnt"].to_numpy()
    out["measured_visits"] = grouped["dur_n"].to_numpy()
    out["seconds_per_visit"] = _ratio(grouped["dur_sum"], grouped["dur_n"])
    out["coverage"] = _ratio(grouped["dur_n"], grouped["cnt"])
    out["dwell_definition"] = TRANSITION_DWELL_DEFINITION
    return out.reset_index(drop=True)
