"""빌드 CLI 인자 해석. 플래그 파싱은 조용히 틀리기 쉬운 자리다."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

from build_cubes import UsageError, parse_args  # noqa: E402

BASE = ["prog", "2026-07-20", "2026-07-26", "top,media"]


def test_parses_the_three_positional_arguments():
    a = parse_args(BASE)
    assert a["start"] == "2026-07-20"
    assert a["end"] == "2026-07-26"
    assert a["services"] == ["top", "media"]


def test_state_dict_and_refresh_default_to_off():
    a = parse_args(BASE)
    assert a["state_dict_version"] is None
    assert a["refresh"] is False


def test_reuses_a_named_state_dict():
    # 사전 버전이 캐시 키에 들어가므로, 재사용해야 날짜만 덧붙일 수 있다.
    a = parse_args(BASE + ["--state-dict=sd_abc123"])
    assert a["state_dict_version"] == "sd_abc123"


def test_refresh_flag():
    assert parse_args(BASE + ["--refresh"])["refresh"] is True


def test_flags_may_come_in_any_order():
    a = parse_args(["prog", "--refresh", "2026-07-20", "--state-dict=sd_x",
                    "2026-07-26", "top"])
    assert a["start"] == "2026-07-20"
    assert a["end"] == "2026-07-26"
    assert a["services"] == ["top"]
    assert a["state_dict_version"] == "sd_x"
    assert a["refresh"] is True


def test_services_are_trimmed_and_blanks_dropped():
    a = parse_args(["prog", "2026-07-20", "2026-07-26", "top, media ,,"])
    assert a["services"] == ["top", "media"]


@pytest.mark.parametrize("argv", [
    ["prog"],
    ["prog", "2026-07-20"],
    ["prog", "2026-07-20", "2026-07-26"],
    ["prog", "2026-07-20", "2026-07-26", "top", "extra"],
])
def test_wrong_positional_count_is_rejected(argv):
    with pytest.raises(UsageError, match="위치 인자"):
        parse_args(argv)


def test_unknown_flag_is_rejected_rather_than_treated_as_a_service():
    # 조용히 위치 인자로 흘러들어가면 서비스 목록이 오염된다.
    with pytest.raises(UsageError, match="모르는 플래그"):
        parse_args(BASE + ["--dry-run"])


def test_empty_state_dict_version_is_rejected():
    with pytest.raises(UsageError, match="--state-dict"):
        parse_args(BASE + ["--state-dict="])


def test_empty_service_list_is_rejected():
    with pytest.raises(UsageError, match="서비스 목록"):
        parse_args(["prog", "2026-07-20", "2026-07-26", " , "])
