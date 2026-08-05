import pandas as pd

from dashboard.render import headline_cards, page_slice, envelope_summary


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


def test_headline_cards_shows_infinity():
    """screen_flow 의 기대 걸음 수는 이탈 못하는 화면이 있으면 inf 다 — 크래시가 아니라 표시해야 한다."""
    assert headline_cards({"mean_expected_steps": float("inf")}) == [("mean_expected_steps", "∞")]
    assert headline_cards({"x": float("-inf")}) == [("x", "-∞")]


def test_page_slice_returns_the_page_rows_and_page_count():
    frame = pd.DataFrame({"x": range(120)})
    rows, n_pages = page_slice(frame, page=0, page_size=50)
    assert list(rows["x"]) == list(range(50))
    assert n_pages == 3          # ceil(120/50)


def test_page_slice_second_page():
    frame = pd.DataFrame({"x": range(120)})
    rows, _ = page_slice(frame, page=1, page_size=50)
    assert list(rows["x"]) == list(range(50, 100))


def test_page_slice_last_page_is_partial():
    frame = pd.DataFrame({"x": range(120)})
    rows, _ = page_slice(frame, page=2, page_size=50)
    assert list(rows["x"]) == list(range(100, 120))


def test_page_slice_clamps_out_of_range_page():
    """손댄 URL 로 페이지가 범위를 넘으면 마지막 페이지로 떨군다 — 크래시 대신."""
    frame = pd.DataFrame({"x": range(10)})
    rows, n_pages = page_slice(frame, page=99, page_size=50)
    assert n_pages == 1
    assert list(rows["x"]) == list(range(10))


def test_page_slice_empty_frame_is_one_page():
    frame = pd.DataFrame({"x": []})
    rows, n_pages = page_slice(frame, page=0, page_size=50)
    assert len(rows) == 0
    assert n_pages == 1


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
