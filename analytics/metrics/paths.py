"""n-gram 경로 지표. `path` 큐브를 읽는 순수 함수.

**`(other)` 행은 경로가 아니라 컷의 크기다.** 세그먼트×n 마다 상위 200 만 남기고 나머지를
그 한 행에 접었으므로, 순위에 섞으면 1위가 될 수도 있다.
"""
from __future__ import annotations

import pandas as pd

# `path` 큐브가 잘린 꼬리를 담는 행. `analytics/cube/sql.py` 의 `OTHER_PATH` 와 같은 값이다.
OTHER_PATH = "(other)"
# `(other)` 가 이 비중을 넘으면 상위 200 이 대표성을 잃는다.
TAIL_DOMINATES_ABOVE = 0.5


def _one_n(paths: pd.DataFrame, n: int | None) -> pd.DataFrame:
    """`n` 하나만 골라 낸다. 섞으면 거부한다."""
    if n is None:
        raise ValueError(
            "read one n at a time: n=3 and n=4 are different populations and pooling "
            "them counts the same visit more than once"
        )
    rows = paths[paths["n"] == n]
    if rows.empty:
        raise KeyError(f"no rows for n={n}; present: {sorted(set(paths['n']))}")
    return rows


def path_coverage(paths: pd.DataFrame, n: int) -> float:
    """상위 경로가 실제로 덮는 비중 = `1 - (other) / 전체`.

    `(other)` 행이 아예 없으면 컷에 안 걸린 세그먼트라 **1.0** 이다 — NaN 이 아니다.
    """
    rows = _one_n(paths, n)
    total = float(rows["cnt"].sum())
    if total <= 0:
        return float("nan")
    tail = float(rows.loc[rows["path"] == OTHER_PATH, "cnt"].sum())
    return 1.0 - tail / total


def top_paths(paths: pd.DataFrame, n: int) -> pd.DataFrame:
    """`n` 걸음 경로 순위. `(other)` 를 뺀 목록이고 비중은 **컷 이전 전체** 기준이다.

    `(other)` 를 순위에서 빼는 이유는 그게 경로가 아니라 컷의 크기이기 때문이다 —
    실측에서 n=4 는 `(other)` 가 90 대 10 으로 1위가 된다. 반대로 **비중의 분모에서는
    빼지 않는다**: 상위 200 안에서만 정규화하면 남은 값이 부푼다.

    `attrs` 에 컷의 크기를 함께 싣는다 — 커버리지 0.1 이 "200개가 꼬리 전부" 인지
    "9,000개를 잘랐" 는지로 해석이 완전히 갈린다.

    **`attrs` 는 pandas 연산에서 쉽게 사라진다.** `copy()` 는 보존하지만 `merge`·`concat`
    은 아니다. 분석층으로 올릴 때는 `attrs` 가 아니라 `AnalysisResult.headline` 에 담는다.
    """
    rows = _one_n(paths, n)
    total = float(rows["cnt"].sum())
    out = rows[rows["path"] != OTHER_PATH].copy()
    out["share"] = out["cnt"] / total if total > 0 else float("nan")
    out = out.sort_values("cnt", ascending=False, ignore_index=True)
    coverage = path_coverage(paths, n)
    out.attrs["coverage"] = coverage
    out.attrs["tail_dominates"] = bool(1.0 - coverage > TAIL_DOMINATES_ABOVE)
    out.attrs["distinct_dropped"] = int(
        rows.loc[rows["path"] == OTHER_PATH, "distinct_dropped"].sum()
    )
    return out
