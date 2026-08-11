from api.glossary import (
    analysis_desc,
    analysis_label,
    axis_help,
    axis_value_label,
    column_help,
    column_label,
    metric_help,
    metric_label,
    value_label,
    warning_label,
)


def test_metric_label_and_help():
    assert metric_label("mean_expected_steps") == "평균 기대 걸음 수"
    assert "떠나기까지" in metric_help("mean_expected_steps")


def test_unknown_metric_falls_back():
    assert metric_label("nope") == "nope"
    assert metric_help("nope") == ""


def test_column_label_and_help():
    assert column_label("pi") == "체류 비중"
    assert "정상분포" in column_help("pi")
    assert column_label("weird") == "weird"


def test_analysis_label_and_desc():
    assert analysis_label("markov_order_test") == "1차 마르코프 검정"
    assert "직전 화면" in analysis_desc("markov_order_test")
    assert analysis_desc("nope") == ""


def test_warning_label():
    assert warning_label("screens_lumped_into_other") == "화면 이름 뭉침"
    assert warning_label("unknown_check") == "unknown_check"


def test_value_label():
    assert value_label("(other)") == "(기타 화면)"
    assert value_label("top/엠탑조회") == "top/엠탑조회"


def test_axis_value_label():
    assert axis_value_label("service_type", "MA") == "모바일 앱(MA)"
    assert axis_value_label("service_type", "") == "전체"
    assert axis_value_label("os", "unknown_os") == "unknown_os"
    assert axis_help("os") != ""
