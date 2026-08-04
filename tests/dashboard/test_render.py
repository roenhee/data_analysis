import pandas as pd

from dashboard.render import headline_cards, table_slice, envelope_summary


def test_headline_cards_format_label_value():
    cards = headline_cards({"mean_expected_steps": 8.0829, "mean_exit_prob": 0.1407})
    assert cards == [
        ("mean_expected_steps", "8.08"),
        ("mean_exit_prob", "0.14"),
    ]


def test_headline_cards_skip_nan():
    """NaN headline(예: 슬라이스의 uv)은 카드로 내지 않는다."""
    cards = headline_cards({"sessions": 1000.0, "uv": float("nan")})
    assert cards == [("sessions", "1,000")]


def test_table_slice_takes_top_n():
    frame = pd.DataFrame({"x": range(50)})
    assert len(table_slice(frame, 10)) == 10
    assert len(table_slice(frame, 999)) == 50   # 최대는 프레임 크기


def test_table_slice_zero_or_negative_is_empty():
    frame = pd.DataFrame({"x": range(5)})
    assert len(table_slice(frame, 0)) == 0


def test_envelope_summary_pulls_the_key_fields():
    envelope = {
        "warnings": [{"check_name": "screens_lumped_into_other"}],
        "coverage": {"dwell": 0.565},
        "state_dict_version": "sd_2ab5",
        "present_dates": ["2026-07-14", "2026-07-28"],
    }
    got = envelope_summary(envelope)
    assert got["warnings"] == ["screens_lumped_into_other"]
    assert got["state_dict_version"] == "sd_2ab5"
    assert got["n_dates"] == 2
