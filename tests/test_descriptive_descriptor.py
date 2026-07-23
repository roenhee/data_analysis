from data_layer.skills_registry import load_skills_registry
from skills.descriptive.descriptor import register


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
