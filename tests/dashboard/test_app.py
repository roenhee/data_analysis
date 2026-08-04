from dashboard.app import safe_tab


def test_safe_tab_keeps_valid():
    assert safe_tab("action", ["overview", "action"]) == "action"


def test_safe_tab_falls_back_on_unknown():
    assert safe_tab("garbage", ["overview", "action"]) == "overview"
