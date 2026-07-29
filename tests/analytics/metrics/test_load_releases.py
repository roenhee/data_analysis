"""배포일 로더. OS 마다 배포일이 다른 것이 이 파일의 존재 이유다."""
import json
from pathlib import Path

import pytest

from analytics.metrics.load import load_releases

CONF = Path("examples/config/releases.json")


def test_without_an_os_the_later_release_wins():
    """OS 를 안 좁힌 비교는 보수적으로 늦은 쪽을 컷오프로 쓴다.

    9.0.1 은 android 04-01, ios 03-25 로 일주일 차이가 난다. 이른 쪽을 쓰면
    03-25~03-31 의 android 트래픽이 "배포 전" 인데도 비교에 들어간다.
    """
    assert load_releases()["9.0.1"] == "2026-04-01"


def test_an_os_picks_that_platforms_date():
    assert load_releases(os="ios")["9.0.1"] == "2026-03-25"
    assert load_releases(os="android")["9.0.1"] == "2026-04-01"


def test_a_version_absent_on_that_os_is_omitted():
    # 9.0.2 는 iOS 전용이다. android 로 물으면 없어야 한다.
    assert "9.0.2" not in load_releases(os="android")
    assert "9.0.2" in load_releases(os="ios")


def test_versions_released_on_both_agree_when_the_dates_match():
    for os_ in (None, "android", "ios"):
        assert load_releases(os=os_)["9.5.1"] == "2026-07-26"


def test_a_version_absent_from_the_source_document_records_where_it_came_from():
    """9.4.2 는 데이터에서 두 번째로 큰 버전인데 배포 이력 문서에 없었다.

    사용자가 날짜를 알려줘 채웠고, 그 출처가 파일에 남아 있어야 나중에 문서와 어긋난
    이유를 알 수 있다.
    """
    meta = json.loads(CONF.read_text())["app_versions"]["9.4.2"]
    assert meta["android"] == "2026-07-06"
    assert "source" in meta


def test_the_shipped_config_still_records_what_is_missing():
    raw = json.loads(CONF.read_text())
    # 6.9.x 는 배포 이력 문서 시작(7.4.0) 이전이라 여전히 없다.
    assert any("6.9" in m for m in raw["missing"])


def test_a_source_note_is_not_mistaken_for_a_release_date():
    # 9.4.2 의 meta 에는 android/ios 말고 source 도 있다. 날짜로 새면 안 된다.
    assert load_releases()["9.4.2"] == "2026-07-06"


def test_the_shipped_config_names_its_source():
    assert "atlassian" in json.loads(CONF.read_text())["source"]
