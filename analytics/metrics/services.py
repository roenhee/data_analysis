"""화면 상태에서 서비스를 되찾는다.

전이 큐브에는 `service_code` 컬럼이 **없다.** 화면 이름이
`service_code || '/' || action_name` 으로 만들어지므로(`analytics/cube/sql.py`) 접두어가
곧 서비스다. 그 사실을 아는 곳을 이 모듈 하나로 묶는다 — 분석마다 `split("/")` 를 흩뿌리면
`START`·`EXIT` 처리가 갈리고, 없는 서비스가 조용히 생긴다.

**`service_code` 를 축으로 올리는 것과 다르다.** 세션 44.7%가 여러 서비스에 걸쳐 있어서
축으로 두면 세션이 쪼개진다. 접두어에서 읽으면 "그 **화면**의 서비스" 라 세션을 건드리지 않는다.

`service_type`(`MA`·`MW`·`PW`)과 혼동하지 말 것 — 그쪽은 진짜 축이고 다른 것을 잰다.
"""
from __future__ import annotations

import pandas as pd

# 화면이 아닌 상태. 전이 큐브가 세션 경계를 표현하려고 넣은 것이다.
NON_SCREEN_STATES = ("START", "EXIT")


def service_of(state: object) -> str | None:
    """화면 상태의 서비스. 화면이 아니면 `None`.

    서비스 코드에는 `/` 가 없으므로 **첫** 슬래시로 자른다 — 화면 이름에 슬래시가 있어도
    서비스는 맞는다.
    """
    if state is None or pd.isna(state):
        return None
    text = str(state)
    if text in NON_SCREEN_STATES:
        return None
    service, sep, _ = text.partition("/")
    return service if sep else None


def service_mix(edges: pd.DataFrame, measure: str = "cnt") -> dict[str, float]:
    """`{서비스: 비중}`. 분모는 **화면에서 출발한** 전이다.

    `START` 를 분모에 넣으면 세션 수가 비중을 지배한다 — 방문 가중 지표가 무엇으로 구성됐는지
    말하려는 것이므로 화면 출발 전이가 맞는 분모다.

    합산 지표가 어느 서비스에 붙어 있는지 봉투가 말하게 하려고 만들었다. 실측 15일에서
    top 61.8% 대 content_v 2.1% 이고, 그 사실이 없으면 합산값이 "앱 전체" 로 읽힌다.
    """
    if "from_state" not in edges.columns or measure not in edges.columns:
        return {}
    frame = edges[["from_state", measure]].copy()
    frame["service"] = [service_of(s) for s in frame["from_state"]]
    frame = frame[frame["service"].notna()]
    total = float(frame[measure].sum())
    if total <= 0:
        return {}
    grouped = frame.groupby("service")[measure].sum()
    return {str(k): float(v / total) for k, v in grouped.items()}
