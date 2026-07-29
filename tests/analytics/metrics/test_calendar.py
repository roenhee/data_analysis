import json
from pathlib import Path

import pytest

from analytics.metrics.calendar import (
    HOLIDAY, WEEKDAY, WEEKEND, UnverifiedWindowError, day_kind, split_by_kind,
)

HOLIDAYS = {"2026-07-17"}


def test_a_normal_weekday_is_a_weekday():
    assert day_kind("2026-07-16", HOLIDAYS) == WEEKDAY   # 목


def test_saturday_and_sunday_are_weekend():
    assert day_kind("2026-07-18", HOLIDAYS) == WEEKEND   # 토
    assert day_kind("2026-07-19", HOLIDAYS) == WEEKEND   # 일


def test_a_holiday_is_neither_weekday_nor_weekend():
    """공휴일은 주말과 다른 신호다 — 세션은 평일급인데 체류만 -30.9% 떨어진다."""
    assert day_kind("2026-07-17", HOLIDAYS) == HOLIDAY   # 금요일이지만 제헌절


def test_a_holiday_falling_on_a_weekend_is_reported_as_a_holiday():
    # 겹치면 공휴일이 이긴다. 둘 다로 세면 같은 날이 두 버킷에 들어간다.
    assert day_kind("2026-08-15", {"2026-08-15"}) == HOLIDAY   # 토요일


def test_split_by_kind_buckets_every_date_exactly_once():
    dates = ["2026-07-16", "2026-07-17", "2026-07-18", "2026-07-19", "2026-07-20"]
    got = split_by_kind(dates, HOLIDAYS)
    assert got[WEEKDAY] == ["2026-07-16", "2026-07-20"]
    assert got[HOLIDAY] == ["2026-07-17"]
    assert got[WEEKEND] == ["2026-07-18", "2026-07-19"]
    assert sum(len(v) for v in got.values()) == len(dates)


def test_split_rejects_dates_outside_the_verified_window():
    """목록이 불완전한 구간을 조용히 '평일'로 분류하면 안 된다.

    음력 공휴일(설날·추석)은 config 에 아직 없다. 그 구간을 평일로 세면 평균이
    끌려가는데, 그게 바로 07-17 을 평일로 셌다가 584.2초로 잘못 보고한 실패다.
    """
    with pytest.raises(UnverifiedWindowError, match="2026-02-01"):
        split_by_kind(["2026-02-01"], HOLIDAYS, verified=[("2026-07-14", "2026-07-27")])


def test_split_passes_when_every_date_is_inside_a_verified_window():
    got = split_by_kind(
        ["2026-07-16", "2026-07-17"], HOLIDAYS,
        verified=[("2026-07-14", "2026-07-27")],
    )
    assert got[HOLIDAY] == ["2026-07-17"]


def test_no_verified_windows_means_no_check():
    # 검증 구간을 안 주면 호출자가 책임진다. 기본값이 막지는 않는다.
    got = split_by_kind(["2026-02-01"], HOLIDAYS)
    assert sum(len(v) for v in got.values()) == 1


def test_the_shipped_config_parses_and_covers_the_backfill_window():
    raw = json.loads(Path("examples/config/holidays_kr.json").read_text())
    assert "2026-07-17" in raw["holidays"]
    assert raw["verified_windows"] == [["2026-07-14", "2026-07-27"]]
    # 목록이 불완전하다는 사실이 파일에 남아 있어야 한다.
    assert raw["missing"], "음력 공휴일이 빠졌다는 표시가 사라졌다"
