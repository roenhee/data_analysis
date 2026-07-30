"""화면 안의 행동 분포. `action` 큐브를 읽는 순수 함수.

`action` 큐브는 롤업 행이 없는 평범한 `GROUP BY` 라 `cnt` 를 그냥 합해도 된다 —
세션 큐브의 `GROUPING SETS` 와 다르다. `full_combination_rows` 를 통과시켜도 전체가
그대로 나온다.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from analytics.metrics.services import NON_SCREEN_STATES


def click_share(
    actions: pd.DataFrame, by: tuple[str, ...] = ("action_kind",)
) -> pd.DataFrame:
    """화면별 `by` 조합의 클릭 건수와 **그 화면 안에서의** 비중.

    **전역으로 정규화하지 않는다.** 트래픽이 많은 화면이 분포를 지배해서 작은 화면의 행동
    구성이 지워진다 — 실측에서 top 이 클릭의 대부분을 차지한다. 화면 안에서 정규화하면
    "이 화면에 들어온 사람은 무엇을 누르나" 가 되어 화면끼리 견줄 수 있다.

    `other` 버킷(사전 밖 값)을 빼지 않는다. 빼면 분모가 줄어 남은 값이 부푼다 —
    화면의 `/other` 와 같은 규약이다. 비율과 함께 `cnt` 를 낸다: 소비자가 검산할 수 있어야
    한다.
    """
    keys = ["screen", *by]
    if actions.empty:
        return pd.DataFrame(columns=[*keys, "cnt", "share"])
    grouped = actions.groupby(keys, as_index=False, observed=True)["cnt"].sum()
    per_screen = grouped.groupby("screen")["cnt"].transform("sum")
    grouped["share"] = grouped["cnt"] / per_screen
    return grouped.sort_values(
        ["screen", "cnt"], ascending=[True, False], ignore_index=True
    )


def clicks_per_visit(actions: pd.DataFrame, edges: pd.DataFrame) -> pd.DataFrame:
    """화면별 방문당 클릭 수. **두 큐브를 화면 이름으로 조인한다.**

    `action` 큐브의 `screen` 과 `transition` 큐브의 `from_state` 가 같은 식으로 만들어져
    있어서 가능하다(`docs/superpowers/measurements/2026-07-30-screen-namespace.md` 의 결정).
    `common.page` 로 귀속했다면 이 지표는 존재할 수 없다 — 물량 79~99.5%에서 두 이름 공간의
    대응이 깨진다.

    방문 수는 그 화면에서 **출발한** 전이 수다. 방문이 없으면 `NaN` 이다 — `inf` 로 내면
    그럴듯한 거짓말이고, 0 으로 내면 "안 누른다" 와 "방문을 모른다" 가 섞인다.

    **`START`·`EXIT` 는 전이 큐브에 있어도 분모로 쓰지 않는다.** 실큐브에서 `START` 는
    from_state 로 3억 8,276만 건이 있는데 그건 세션 수이지 화면 방문 수가 아니다. 그대로
    나누면 "세션 시작 시점의 방문당 클릭" 이라는 없는 값이 그럴듯하게 나온다 — 첫 화면
    이전 클릭은 `action` 큐브에서 `START` 에 붙으므로 실제로 그 행이 생긴다.
    """
    clicks = actions.groupby("screen", as_index=False, observed=True)["cnt"].sum()
    screens_only = edges[~edges["from_state"].isin(NON_SCREEN_STATES)]
    visits = (
        screens_only.groupby("from_state", observed=True)["cnt"]
        .sum()
        .rename("visits")
        .rename_axis("screen")
        .reset_index()
    )
    out = clicks.merge(visits, on="screen", how="left")
    denominator = out["visits"].to_numpy(dtype=float)
    # `np.where` 는 양쪽 분기를 **다 계산해서** 0 으로 나누는 경고가 먼저 난다.
    # `np.divide(..., where=)` 는 조건이 참인 자리만 계산한다.
    ratio = np.full(len(out), np.nan)
    np.divide(
        out["cnt"].to_numpy(dtype=float), denominator,
        out=ratio, where=denominator > 0,
    )
    out["clicks_per_visit"] = ratio
    return out.sort_values("cnt", ascending=False, ignore_index=True)
