"""compare: on 축의 두 값을 비교해 JSON 으로 낸다. 실큐브(7서비스 22일)."""
import pytest

from api import compare

_SERVICES = ("top", "media", "entertain", "sports", "content_v", "search", "agorax")
_SDV = "sd_68461a6e4fc6ccac"


def _segment(**axes):
    return {"services": list(_SERVICES), "dates": [], **axes}


def test_run_compare_gender_on_session_trend():
    out = compare.run_compare(
        "session_trend", "2026-07-14", "2026-07-16",
        _segment(), on="gender", a="F", b="M", param_values={},
        state_dict_version=_SDV,
    )
    # 기존 분석 계약 그대로(headline·columns·rows·viz·envelope) + compare 블록.
    assert out["headline"], "pooled 델타가 headline 으로 나와야 한다"
    assert out["rows"], "날짜별 델타 행이 있어야 한다"
    c = out["compare"]
    assert c["on"] == "gender" and c["a"] == "F" and c["b"] == "M"
    assert isinstance(c["weight_skew"], float)
    assert isinstance(c["sign_disagrees"], bool)
    assert c["dates_used"], "비교에 쓴 날짜가 있어야 한다"


def test_run_compare_rejects_reversed_range():
    with pytest.raises(ValueError):
        compare.run_compare(
            "session_trend", "2026-07-16", "2026-07-14",
            _segment(), on="gender", a="F", b="M", param_values={},
            state_dict_version=_SDV,
        )
