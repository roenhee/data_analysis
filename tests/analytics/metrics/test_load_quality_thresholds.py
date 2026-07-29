"""품질 임계치 로더. 값마다 실측 근거가 파일 안에 있어야 하는 것이 이 파일의 요점이다."""
import json
from pathlib import Path

from analytics.cube.sql import QUALITY_CHECKS
from analytics.metrics.load import load_quality_thresholds

CONF = Path("examples/config/quality_thresholds.json")

# 임계치를 안 거는 검사와 그 이유. 이유가 있어야 목록에 넣는다.
UNTHRESHOLDED = {"screen_other_ratio"}


def test_every_check_is_either_thresholded_or_deliberately_not():
    """검사를 새로 추가하고 임계치를 잊는 것이 이 테스트가 막는 것이다."""
    thresholded = set(load_quality_thresholds())
    assert thresholded | UNTHRESHOLDED == set(QUALITY_CHECKS)


def test_every_threshold_carries_its_measured_basis():
    """근거 없는 숫자가 권위를 갖는 것을 막는다 — 값만 있고 basis 가 없으면 실패."""
    raw = json.loads(CONF.read_text())
    for name, meta in raw["thresholds"].items():
        assert isinstance(meta["limit"], (int, float)), name
        assert meta.get("basis"), f"{name} 에 근거가 없다"
        assert "실측" in meta["basis"], f"{name} 의 근거가 측정에서 오지 않았다"


def test_the_unthresholded_checks_are_explained_in_the_file():
    raw = json.loads(CONF.read_text())
    for name in UNTHRESHOLDED:
        assert name in raw["_absent_checks"]


def test_the_comparison_level_is_recorded_with_the_values():
    """임계치의 근거가 집계된 비율이므로 어느 수준에 대는지가 값과 함께 있어야 한다."""
    raw = json.loads(CONF.read_text())
    assert "service_code" in raw["_level"] or "서비스" in raw["_level"]


# (서비스, 날짜) 수준 실측. 임계치를 이 사이에 어중간하게 두면 정상 변동의 상위 몇 일만
# 걸려서 드리프트 탐지기도 상시 표시도 아닌 값이 된다.
MEASURED = {                        # 검사: (전체 최댓값, 나쁜 무리의 최솟값 또는 None)
    "null_action_name": (0.1912, None),
    "pageview_null_kind": (0.0741, None),
    "session_span_exceeds_timeout": (0.0044, None),
    "exit_without_appexit": (0.1114, None),
    "session_no_screen": (0.3262, 0.1960),          # top 이 이분된 나쁜 쪽
    "screen_without_dwell": (1.0000, 1.0000),       # search 는 항상 100%
    "page_name_ambiguous": (0.7930, 0.2714),        # sports·search
}


def test_each_threshold_is_a_drift_detector_or_a_standing_flag_not_in_between():
    """관측 최댓값 위(드리프트) 아니면 나쁜 무리 최솟값 아래(상시 표시)여야 한다.

    사이에 있으면 정상 변동의 상위 몇 일만 걸린다 — 실제로 `session_no_screen` 0.30 이
    top 의 0.1960~0.3262 안에 있어서 15일 중 3일만 걸리고 있었다.
    """
    limits = load_quality_thresholds()
    for name, (observed_max, bad_floor) in MEASURED.items():
        limit = limits[name]
        drift = limit > observed_max
        standing = bad_floor is not None and limit < bad_floor
        assert drift or standing, (
            f"{name}: 임계치 {limit} 가 관측 최댓값 {observed_max} 아래이면서 "
            f"나쁜 무리 최솟값 {bad_floor} 위다 — 정상 변동의 일부만 걸린다"
        )
