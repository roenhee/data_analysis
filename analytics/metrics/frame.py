"""큐브 프레임 다루기. 파일시스템도 config 도 모르는 순수 모듈.

**세션 큐브에는 롤업 행이 섞여 있다.** `GROUPING SETS` 로 만들어져 전체 조합 행 +
축 하나씩 접은 행 + `(period)` + `()` 가 한 파일에 있고, 접힌 축은 NULL 이다.
필터 없이 합산하면 같은 세션을 여러 번 센다. 전이·품질 큐브는 평범한 `GROUP BY` 라
롤업 행이 없으므로 `full_combination_rows` 가 전체를 그대로 돌려준다.
"""
from __future__ import annotations

import pandas as pd

# 큐브에서 가산이 아닌 측정값. 롤업은 큐브에 이미 들어 있으므로 거기서 읽는다.
NON_ADDITIVE = ("uv",)


class NonAdditiveMeasureError(ValueError):
    """가산이 아닌 측정값을 합산하려 했다."""


def full_combination_rows(df: pd.DataFrame, axes: tuple[str, ...]) -> pd.DataFrame:
    """축이 하나도 접히지 않은 행만 남긴다."""
    present = [a for a in axes if a in df.columns]
    if not present:
        return df
    return df.dropna(subset=present)


def rollup_rows(
    df: pd.DataFrame, axes: tuple[str, ...], folded: tuple[str, ...]
) -> pd.DataFrame:
    """`folded` 축이 **정확히** 접힌 롤업 행만 남긴다.

    접힌 축은 NULL, 나머지 축은 non-NULL 이어야 한다. 둘 중 하나만 보면 여러
    grouping set 이 섞여 들어와 합계가 부푼다.
    """
    unknown = set(folded) - set(axes)
    if unknown:
        raise KeyError(f"not an axis: {sorted(unknown)}")
    out = df
    for axis in axes:
        if axis not in out.columns:
            continue
        if axis in folded:
            out = out[out[axis].isna()]
        else:
            out = out[out[axis].notna()]
    return out


def select_segment(df: pd.DataFrame, **filters) -> pd.DataFrame:
    """축 값으로 세그먼트를 고른다. 값 하나 또는 목록."""
    out = df
    for column, wanted in filters.items():
        if column not in out.columns:
            raise KeyError(f"no such column: {column!r}")
        if isinstance(wanted, (list, tuple, set)):
            out = out[out[column].isin(list(wanted))]
        else:
            out = out[out[column] == wanted]
    return out


def additive_sum(df: pd.DataFrame, measure: str) -> float:
    """가산 측정값을 합산한다. 비가산이면 거부한다."""
    if measure in NON_ADDITIVE:
        raise NonAdditiveMeasureError(
            f"{measure!r} is not additive — the same user counted on two days is one "
            "user, not two; read the pre-computed rollup row from the cube instead "
            "(see rollup_rows)"
        )
    return float(df[measure].sum())
