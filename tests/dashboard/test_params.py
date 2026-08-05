from dashboard.params import Param, coerce, params_for, required_names


def test_path_ranking_requires_n():
    specs = params_for("path_ranking")
    assert specs == [Param("n", "int", required=True, choices=(3, 2, 4, 5))]
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


def test_coerce_choice_becomes_a_tuple():
    # click_distribution.by is tuple[str,...]; a single choice must still be a tuple
    assert coerce("click_distribution", {"by": "action_kind"}) == {"by": ("action_kind",)}


def test_coerce_multi_choice_splits_on_comma():
    assert coerce("click_distribution", {"by": "layer1,layer2"}) == {"by": ("layer1", "layer2")}


def test_coerce_int_param():
    assert coerce("path_ranking", {"n": "4"}) == {"n": 4}


def test_coerce_float_param():
    assert coerce("screen_flow", {"damping": "0.85"}) == {"damping": 0.85}


def test_coerce_pair_param():
    assert coerce("screen_flow", {"exit_within": "1,3"}) == {"exit_within": (1, 3)}


def test_coerce_screen_param_stays_string():
    assert coerce("reachability", {"source": "top/홈탭_진입"}) == {"source": "top/홈탭_진입"}


def test_coerce_ignores_blank_values():
    # blank means "use the analysis default" — don't pass it at all
    assert coerce("screen_flow", {"damping": ""}) == {}
