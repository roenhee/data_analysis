from data_layer.skills_registry import load_skills_registry, register_skill


def _desc(name="markov"):
    return {
        "name": name,
        "description": "행동 로그 마르코프 분석",
        "invocation": "markov 스킬 실행 후 기간/시드 지정",
        "expected_params": {"window": "[start, end]", "seed": "int"},
    }


def test_register_and_load(config):
    register_skill(config, _desc("markov"))
    register_skill(config, _desc("funnel"))
    reg = load_skills_registry(config)
    assert {s["name"] for s in reg} == {"markov", "funnel"}


def test_register_upserts_by_name(config):
    register_skill(config, _desc("markov"))
    updated = _desc("markov")
    updated["description"] = "업데이트됨"
    register_skill(config, updated)
    reg = load_skills_registry(config)
    hits = [s for s in reg if s["name"] == "markov"]
    assert len(hits) == 1 and hits[0]["description"] == "업데이트됨"


def test_load_empty_when_absent(config):
    assert load_skills_registry(config) == []
