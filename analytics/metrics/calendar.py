"""날짜를 평일·주말·공휴일로 나눈다. 파일시스템도 config 도 모르는 순수 모듈.

**공휴일은 주말과 다른 신호다.** 실측(2026-07-17 제헌절, 6서비스):

| | 세션 (평일 대비) | 세션당 체류 (평일 대비) |
|---|---|---|
| 평일 9일 | 35,124,350 | 602.8초 |
| 공휴일 1일 | −8.5% | **−30.9%** |
| 주말 4일 | −22.8% | −23.5% |

주말은 세션과 체류가 같이 떨어지는데 공휴일은 **세션이 평일 수준인데 체류만 급락**한다
(주말보다도 짧다). 평소만큼 들어오되 훨씬 짧게 머문다.

공휴일을 평일 버킷에 넣으면 평일 평균이 끌려 내려간다 — 실제로 평일 체류를 584.2초로
보고했다가 602.8초로 정정했고, 그 전에는 07-17 을 "금요일인데 주말처럼 행동하는 이상치"로
오해해 데이터 결함을 의심했다.
"""
from __future__ import annotations

from datetime import date as _date

WEEKDAY = "평일"
WEEKEND = "주말"
HOLIDAY = "공휴일"


class UnverifiedWindowError(ValueError):
    """공휴일 목록이 검증되지 않은 구간의 날짜를 분류하려 했다."""


def day_kind(day: str, holidays: set[str]) -> str:
    """`YYYY-MM-DD` 를 평일·주말·공휴일 중 하나로.

    공휴일이 주말과 겹치면 **공휴일이 이긴다.** 둘 다로 세면 같은 날이 두 버킷에 들어가
    합계가 안 맞는다.
    """
    if day in holidays:
        return HOLIDAY
    return WEEKEND if _date.fromisoformat(day).weekday() >= 5 else WEEKDAY


def split_by_kind(
    days: list[str],
    holidays: set[str],
    verified: list[tuple[str, str]] | None = None,
) -> dict[str, list[str]]:
    """날짜를 종류별로 묶는다. 각 날짜는 정확히 한 버킷에 들어간다.

    `verified` 를 주면 그 구간 밖의 날짜를 **거부한다.** 음력 공휴일(설날·부처님오신날·
    추석)과 대체공휴일은 config 에 아직 없어서, 목록이 불완전한 구간을 조용히 '평일' 로
    분류하면 평균이 끌려간다. 검증 구간을 안 주면 검사하지 않는다 — 호출자 책임이다.
    """
    if verified:
        outside = [
            d for d in days
            if not any(start <= d <= end for start, end in verified)
        ]
        if outside:
            raise UnverifiedWindowError(
                f"{len(outside)} date(s) fall outside the verified holiday windows "
                f"({', '.join(sorted(outside)[:5])}); the holiday list is incomplete "
                "there — lunar holidays and substitute days are not computed, and "
                "bucketing a holiday as a weekday drags the weekday average"
            )
    out: dict[str, list[str]] = {WEEKDAY: [], WEEKEND: [], HOLIDAY: []}
    for day in sorted(days):
        out[day_kind(day, holidays)].append(day)
    return out
