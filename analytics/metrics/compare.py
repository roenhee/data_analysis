"""세그먼트 비교의 교란 방지. 파일시스템도 config 도 모르는 순수 모듈.

**버전 델타는 이 프로젝트의 주 용도인데, 가장 조용히 틀리는 자리이기도 하다.**

앱 버전은 단계적으로 배포된다. 실측(2026-07-14~28, MA): `9.5.0` 은 07-14 에 2% 로 시작해
07-25 에 91% 에 이르고, `9.5.1` 은 07-26 에 2.1% 로 나타나 07-28 에 63.7% 가 된다. 즉 두
버전이 **같은 날짜 범위에 존재하지 않는다.**

그 상태로 "14일 전체" 를 비교하면 버전 차이가 아니라 **날짜 차이**를 재게 된다. 실측:

| 지표 | 14일 전체 | 겹치는 날짜만 |
|---|---|---|
| 기대 걸음 수 Δ | **+2.9%** | **-0.2%** |
| `top/홈탭_진입` 이탈 Δ | +0.39% | +0.77% |

"9.5.1 에서 세션이 2.9% 길어졌다" 는 그럴듯하고 완전히 틀린 결론이다. 예외도 안 나고
숫자도 멀쩡해 보인다. 그래서 `uv` 합산·부분 빌드와 같은 등급으로 **막는다.**
"""
from __future__ import annotations

import pandas as pd


class ConfoundedComparisonError(ValueError):
    """두 세그먼트가 같은 날짜 위에 없어 델타가 날짜 효과와 뒤섞인다."""


def _dates_of(cube: pd.DataFrame, axis: str, value: str) -> set[str]:
    if axis not in cube.columns:
        raise KeyError(f"no such column: {axis!r}")
    return set(cube.loc[cube[axis] == value, "period"].dropna())


def comparable_dates(
    cube: pd.DataFrame,
    axis: str,
    a: str,
    b: str,
    released: dict[str, str] | None = None,
) -> list[str]:
    """`a` 와 `b` 가 **둘 다** 존재하는 날짜. 없으면 거부한다.

    돌려주는 날짜 수가 적으면(1~2일) 요일 효과를 걷어내지 못하므로 호출자가 판단한다 —
    막지는 않되 몇 일인지는 보이게 한다.

    **날짜 겹침만으로는 부족하다.** 한때 이 함수의 주석은 "물량이 적으면 노이즈가
    커질 뿐 편향은 안 생긴다" 고 적혀 있었는데 **틀렸다.** 겹치는 날 안에서 한쪽 물량이
    특정 날에 쏠려 있으면 카운트를 합친 순간 날짜 교란이 그대로 돌아온다 — 실측에서
    9.5.1 은 전이의 97% 가 07-27 하루에 있고 9.5.0 은 4일에 고루 있어서, 합산 델타가
    "9.5.1 의 07-27" 과 "9.5.0 의 4일 평균" 을 비교하고 있었다(합산 +2.7% vs 07-27 하루
    +4.0%). 그래서 `day_volumes` 와 `weight_skew` 를 함께 보게 한다.

    `released` 를 주면 **배포일 이전 날짜를 제외한다.** 배포 전 트래픽은 적은 표본이
    아니라 **다른 모집단**(테스터)이다 — 실측에서 9.5.1 배포일(2026-07-26) 이전 이틀은
    전이가 4건·308건이었고, 이건 노이즈가 아니라 종류가 다른 데이터다. 등록되지 않은
    버전은 막지 않는다; 호출자가 `day_volumes` 를 보고 판단한다.
    """
    before = {v: _dates_of(cube, axis, v) for v in (a, b)}
    cutoff = None
    if released:
        cutoff = max(
            (released.get(v) for v in (a, b) if released.get(v)), default=None
        )
        if cutoff:
            cube = cube[cube["period"] >= cutoff]
    da, db = _dates_of(cube, axis, a), _dates_of(cube, axis, b)
    for value, dates in ((a, da), (b, db)):
        if dates:
            continue
        # 무엇이 비웠는지 구분해서 말한다 — 원래 없던 것과 배포일로 잘린 것은 다르다.
        if before[value] and cutoff:
            raise ConfoundedComparisonError(
                f"no overlapping dates: every row for {axis}={value!r} "
                f"({min(before[value])}~{max(before[value])}) precedes the release "
                f"cutoff {cutoff}; pre-release traffic is test traffic, a different "
                "population rather than a small sample of the same one"
            )
        raise ConfoundedComparisonError(
            f"{axis}={value!r} does not appear in this cube at all"
        )
    both = sorted(da & db)
    if not both:
        raise ConfoundedComparisonError(
            f"no overlapping dates between {axis}={a!r} ({min(da)}~{max(da)}) and "
            f"{axis}={b!r} ({min(db)}~{max(db)}); a delta across disjoint windows "
            "measures the calendar, not the segment — staged rollouts make this the "
            "normal case for app versions"
        )
    return both


def restrict_to_comparable(
    cube: pd.DataFrame,
    axis: str,
    a: str,
    b: str,
    released: dict[str, str] | None = None,
) -> pd.DataFrame:
    """두 값과 겹치는 날짜만 남긴 프레임. 이걸 비교의 입력으로 쓴다."""
    dates = comparable_dates(cube, axis, a, b, released=released)
    return cube[cube["period"].isin(dates) & cube[axis].isin([a, b])]


def day_volumes(
    cube: pd.DataFrame,
    axis: str,
    a: str,
    b: str,
    measure: str = "cnt",
    released: dict[str, str] | None = None,
) -> pd.DataFrame:
    """겹치는 날짜별로 두 세그먼트의 물량과 점유율.

    **합산 델타 하나만 보면 이게 안 보인다.** 실측에서 07-24 의 9.5.1 은 전이 4건이었고
    그날 델타는 -79.1% 였다 — 숫자만 보면 큰 변화지만 4건짜리다. 표를 같이 내면
    그게 즉시 보인다. 임계치로 거르지 않고 드러내는 이유다.
    """
    dates = comparable_dates(cube, axis, a, b, released=released)
    sub = cube[cube["period"].isin(dates)]
    rows = []
    for day, g in sub.groupby("period"):
        va = float(g.loc[g[axis] == a, measure].sum())
        vb = float(g.loc[g[axis] == b, measure].sum())
        total = float(g[measure].sum())
        rows.append(
            {
                "period": day,
                "a_cnt": va,
                "b_cnt": vb,
                "a_share": va / total if total > 0 else float("nan"),
            }
        )
    return pd.DataFrame(rows).sort_values("period").reset_index(drop=True)


def weight_skew(
    cube: pd.DataFrame,
    axis: str,
    a: str,
    b: str,
    measure: str = "cnt",
    released: dict[str, str] | None = None,
) -> float:
    """두 세그먼트의 **날짜 가중치**가 얼마나 어긋났는가. 0이면 같은 분포다.

    총변동거리(각 날짜 비중 차이의 절반 합). 이게 크면 겹치는 날짜를 강제했는데도
    합산 델타가 날짜 효과를 담고 있다.
    """
    vols = day_volumes(cube, axis, a, b, measure=measure, released=released)
    ta, tb = vols["a_cnt"].sum(), vols["b_cnt"].sum()
    if ta <= 0 or tb <= 0:
        return float("nan")
    return float((vols["a_cnt"] / ta - vols["b_cnt"] / tb).abs().sum() / 2)
