from data_layer.skills_registry import load_skills_registry
from skills.descriptive.descriptor import DESCRIPTOR, register


def test_register_puts_descriptor_in_registry(config):
    register(config)
    reg = load_skills_registry(config)
    match = [s for s in reg if s["name"] == "descriptive"]
    assert len(match) == 1
    assert "uv_pv_by_period" in match[0]["expected_params"]["analysis_type"]
    assert "session_engagement_by_period" in match[0]["expected_params"]["analysis_type"]


def test_register_is_idempotent(config):
    register(config)
    register(config)
    reg = load_skills_registry(config)
    assert sum(1 for s in reg if s["name"] == "descriptive") == 1


def test_descriptor_matches_menu_and_whitelist():
    from skills.descriptive.run import MENU
    from skills.descriptive.sql import BREAKDOWN_WHITELIST
    ep = DESCRIPTOR["expected_params"]
    assert set(ep["analysis_type"]) == set(MENU)
    assert set(ep["breakdown"]) == set(BREAKDOWN_WHITELIST)
