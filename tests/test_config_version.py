from data_layer.config_artifacts import config_version


def test_config_version_stable_and_order_independent():
    d = {"cutoff": 0.95, "mapping": {"A": "A", "B": "other"}}
    s = {"timeout_min": 30}
    v1 = config_version(d, s)
    v2 = config_version({"mapping": {"B": "other", "A": "A"}, "cutoff": 0.95}, {"timeout_min": 30})
    assert v1 == v2
    assert isinstance(v1, str) and len(v1) == 16


def test_config_version_changes_with_dictionary_or_sessionization():
    d = {"cutoff": 0.95}
    s = {"timeout_min": 30}
    base = config_version(d, s)
    assert config_version({"cutoff": 0.90}, s) != base
    assert config_version(d, {"timeout_min": 15}) != base
