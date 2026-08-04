from dashboard.params import Param, params_for, required_names


def test_path_ranking_requires_n():
    specs = params_for("path_ranking")
    assert specs == [Param("n", "int", required=True)]
    assert required_names("path_ranking") == ["n"]


def test_reachability_requires_source_and_target():
    names = [p.name for p in params_for("reachability")]
    assert names == ["source", "target", "max_k"]
    assert required_names("reachability") == ["source", "target"]


def test_click_distribution_has_a_choice():
    (by,) = params_for("click_distribution")
    assert by.name == "by" and by.kind == "choice"
    assert "action_kind" in by.choices


def test_analysis_with_no_params_returns_empty():
    assert params_for("markov_order_test") == []
    assert required_names("markov_order_test") == []


def test_unknown_analysis_returns_empty():
    assert params_for("does_not_exist") == []
