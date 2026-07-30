"""화면 이름 접두어에서 서비스를 되찾는다. `START`·`EXIT` 는 서비스가 없다."""
import numpy as np
import pandas as pd
import pytest

from analytics.metrics.services import service_mix, service_of


def test_the_prefix_is_the_service():
    assert service_of("top/엠탑조회") == "top"
    assert service_of("content_v/contentview") == "content_v"


def test_the_other_bucket_still_belongs_to_its_service():
    """`top/other` 는 "어느 화면인지 모른다" 지 "어느 서비스인지 모른다" 가 아니다."""
    assert service_of("top/other") == "top"


def test_start_and_exit_have_no_service():
    """둘은 화면이 아니라 세션 경계다. 서비스를 붙이면 없는 서비스가 생긴다."""
    assert service_of("START") is None
    assert service_of("EXIT") is None


def test_a_screen_name_containing_a_slash_keeps_its_service():
    """서비스 코드에는 `/` 가 없으므로 **첫** 슬래시로 자른다."""
    assert service_of("media/a/b") == "media"


def test_a_missing_state_has_no_service():
    assert service_of(None) is None
    assert service_of(np.nan) is None


def _edges() -> pd.DataFrame:
    return pd.DataFrame([
        {"from_state": "top/엠탑조회", "to_state": "top/홈탭_진입", "cnt": 600},
        {"from_state": "top/홈탭_진입", "to_state": "media/뉴스", "cnt": 200},
        {"from_state": "media/뉴스", "to_state": "EXIT", "cnt": 200},
        # START 는 화면이 아니라 비중의 분모에 들어가지 않는다.
        {"from_state": "START", "to_state": "top/엠탑조회", "cnt": 5000},
    ])


def test_the_mix_is_the_share_of_screen_originating_transitions():
    """분모는 **화면에서 출발한** 전이다. `START` 를 넣으면 세션 수가 비중을 지배한다."""
    got = service_mix(_edges())
    assert got == {"top": pytest.approx(0.8), "media": pytest.approx(0.2)}


def test_the_mix_sums_to_one():
    assert sum(service_mix(_edges()).values()) == pytest.approx(1.0)


def test_an_empty_frame_gives_an_empty_mix_rather_than_raising():
    """봉투를 만들 때 부르므로 여기서 죽으면 분석 전부가 죽는다."""
    assert service_mix(pd.DataFrame(columns=["from_state", "cnt"])) == {}


def test_a_frame_without_the_columns_gives_an_empty_mix():
    assert service_mix(pd.DataFrame({"period": ["2026-07-27"]})) == {}
