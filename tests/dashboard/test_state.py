from dashboard.state import encode_state, decode_state, DEFAULTS


def test_defaults_round_trip():
    """빈 params 는 기본 상태로 디코딩된다."""
    assert decode_state({}) == DEFAULTS


def test_scalar_round_trip():
    state = {**DEFAULTS, "analysis": "screen_flow", "top": 25}
    assert decode_state(encode_state(state)) == state


def test_axis_list_round_trips_as_csv():
    """세그먼트 축은 다중 선택이라 리스트로 왕복한다(services 와 같은 방식)."""
    state = {**DEFAULTS, "os": ["android", "ios"], "gender": ["F"]}
    encoded = encode_state(state)
    assert encoded["os"] == "android,ios"
    assert decode_state(encoded)["os"] == ["android", "ios"]
    assert decode_state(encoded)["gender"] == ["F"]


def test_services_list_round_trips_as_csv():
    """서비스는 다중이라 콤마로 인코딩된다."""
    state = {**DEFAULTS, "services": ["top", "media"]}
    encoded = encode_state(state)
    assert encoded["services"] == "top,media"
    assert decode_state(encoded)["services"] == ["top", "media"]


def test_date_range_round_trips_as_colon():
    state = {**DEFAULTS, "dates": ["2026-07-14", "2026-07-28"]}
    encoded = encode_state(state)
    assert encoded["dates"] == "2026-07-14:2026-07-28"
    assert decode_state(encoded)["dates"] == ["2026-07-14", "2026-07-28"]


def test_analysis_params_are_prefixed():
    """분석 파라미터는 p_ 접두어로 다른 상태와 안 섞인다."""
    state = {**DEFAULTS, "analysis": "path_ranking", "params": {"n": 4}}
    encoded = encode_state(state)
    assert encoded["p_n"] == "4"
    assert decode_state(encoded)["params"] == {"n": 4}


def test_unknown_keys_are_ignored():
    """URL 에 손댄 낯선 키는 조용히 무시한다 — 화면을 안 깨뜨린다."""
    got = decode_state({"analysis": "screen_flow", "garbage": "x"})
    assert got["analysis"] == "screen_flow"
    assert "garbage" not in got
