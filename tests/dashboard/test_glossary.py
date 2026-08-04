from dashboard.glossary import (
    analysis_desc,
    column_label,
    metric_help,
    metric_label,
)


def test_known_metric_has_korean_label_and_help():
    assert metric_label("mean_expected_steps") == "평균 기대 걸음 수"
    assert "떠나기까지" in metric_help("mean_expected_steps")


def test_unknown_metric_falls_back_to_key():
    assert metric_label("brand_new_metric") == "brand_new_metric"
    assert metric_help("brand_new_metric") == ""


def test_known_column_label():
    assert column_label("exit_prob") == "이탈률"
    assert column_label("pi") == "체류 비중(정상분포)"


def test_unknown_column_falls_back_to_name():
    assert column_label("weird_col") == "weird_col"


def test_analysis_desc_known_and_unknown():
    assert "1차 마르코프" in analysis_desc("markov_order_test")
    assert analysis_desc("does_not_exist") == ""
