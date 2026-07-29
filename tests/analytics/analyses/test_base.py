import pandas as pd
import pytest

from analytics.analyses.base import (
    AnalysisResult,
    ConflictingPublicationError,
    CubeSet,
    IncompleteEnvelopeError,
    UnknownAnalysisError,
    analysis,
    get_analysis,
    list_analyses,
    publish,
)

FULL_ENVELOPE = {
    "state_dict_version": "sd_abc", "services": ["top"],
    "requested_dates": ["2026-07-27"], "present_dates": ["2026-07-27"],
    "missing_dates": [], "is_complete": True, "coverage": {"dwell": 0.57},
    "warnings": [],
}


def _cubes(periods=("2026-07-27",)) -> CubeSet:
    session = pd.DataFrame([
        {"period": p, "service_type": "MA", "os": "android", "gender": "M",
         "age_band": "50", "daypart": "12~17", "app_version": "9.5.1",
         "sessions": 10, "uv": 8, "pv": 40, "events": 100, "duration_sum": 600}
        for p in periods
    ])
    return CubeSet(session=session, transition=None, quality=None,
                   state_dict_version="sd_abc", services=["top"],
                   requested_dates=list(periods), present_dates=list(periods))


def test_cubeset_filters_by_date():
    got = _cubes(("2026-07-27", "2026-07-28")).filter(dates=["2026-07-27"])
    assert set(got.session["period"]) == {"2026-07-27"}
    assert got.present_dates == ["2026-07-27"]


def test_cubeset_filters_by_segment():
    assert len(_cubes().filter(os="android").session) == 1
    assert _cubes().filter(os="ios").session.empty


def test_cubeset_accepts_a_list_of_segment_values():
    assert len(_cubes().filter(os=["android", "ios"]).session) == 1


def test_cubeset_filter_leaves_absent_cubes_absent():
    assert _cubes().filter(os="android").transition is None


def test_cubeset_filter_ignores_a_column_the_cube_does_not_have():
    # 큐브마다 컬럼이 다르다. 전이 큐브엔 uv 가 없다.
    assert len(_cubes().filter(nonexistent="x").session) == 1


def test_a_result_carries_frame_headline_and_envelope():
    r = AnalysisResult(frame=pd.DataFrame({"x": [1]}), headline={"mean": 1.0},
                       envelope=FULL_ENVELOPE)
    assert r.headline["mean"] == 1.0


def test_publish_refuses_an_envelope_missing_coverage(config):
    env = {k: v for k, v in FULL_ENVELOPE.items() if k != "coverage"}
    r = AnalysisResult(frame=pd.DataFrame({"x": [1]}), headline={}, envelope=env)
    with pytest.raises(IncompleteEnvelopeError, match="coverage"):
        publish(config, r, run_id="r1", analysis_type="t", title="x")


def test_publish_refuses_an_envelope_missing_the_dictionary_version(config):
    env = {k: v for k, v in FULL_ENVELOPE.items() if k != "state_dict_version"}
    r = AnalysisResult(frame=pd.DataFrame({"x": [1]}), headline={}, envelope=env)
    with pytest.raises(IncompleteEnvelopeError, match="state_dict_version"):
        publish(config, r, run_id="r1", analysis_type="t", title="x")


def test_publish_round_trips_the_frame(config):
    from data_layer.results import read_result
    r = AnalysisResult(frame=pd.DataFrame({"x": [1, 2]}), headline={"mean": 1.5},
                       envelope=FULL_ENVELOPE)
    rid = publish(config, r, run_id="r1", analysis_type="t", title="x")
    df, env = read_result(config, rid)
    assert df["x"].tolist() == [1, 2]
    assert env["viz"]["headline"]["mean"] == 1.5


def test_the_caveats_line_names_the_service_scope_and_coverage(config):
    from data_layer.results import read_result
    r = AnalysisResult(frame=pd.DataFrame({"x": [1]}), headline={},
                       envelope=FULL_ENVELOPE)
    _, env = read_result(config, publish(config, r, run_id="r1",
                                         analysis_type="t", title="x"))
    assert "top" in env["caveats"]
    assert "57" in env["caveats"]


def test_an_incomplete_window_is_named_in_the_caveats(config):
    from data_layer.results import read_result
    env_in = {**FULL_ENVELOPE, "requested_dates": ["2026-07-27", "2026-07-28"],
              "missing_dates": ["2026-07-28"], "is_complete": False}
    r = AnalysisResult(frame=pd.DataFrame({"x": [1]}), headline={}, envelope=env_in)
    _, env = read_result(config, publish(config, r, run_id="r1",
                                         analysis_type="t", title="x"))
    assert "미빌드" in env["caveats"]


def test_publishing_the_same_thing_twice_yields_one_result(config):
    from data_layer.results import list_results
    r = AnalysisResult(frame=pd.DataFrame({"x": [1]}), headline={},
                       envelope=FULL_ENVELOPE)
    publish(config, r, run_id="r1", analysis_type="t", title="x")
    publish(config, r, run_id="r1", analysis_type="t", title="x")
    assert len(list_results(config, run_id="r1")) == 1


@analysis("dummy_with_knobs")
def _dummy_with_knobs(cubes, horizon: int = 10, damping: float = 0.85, **_):
    return AnalysisResult(frame=pd.DataFrame({"x": [horizon]}), headline={},
                          envelope=FULL_ENVELOPE)


def test_the_registry_records_the_parameters_a_call_was_made_with():
    """발행물이 '무엇이 이 숫자를 만들었나' 를 말해야 한다.

    분석마다 손으로 적으면 하나는 빠뜨리고 그 누락은 조용하다. 레지스트리가 기록한다.
    """
    got = get_analysis("dummy_with_knobs")(_cubes(), horizon=3)
    assert got.params == {"horizon": 3, "damping": 0.85}


def test_default_parameters_are_recorded_too():
    """기본값이 나중에 바뀌면 옛 발행물의 숫자를 재현할 수 없다."""
    got = get_analysis("dummy_with_knobs")(_cubes())
    assert got.params == {"horizon": 10, "damping": 0.85}


def test_the_recorded_parameters_reach_the_published_envelope(config):
    from data_layer.results import read_result
    got = get_analysis("dummy_with_knobs")(_cubes(), horizon=7)
    _, env = read_result(config, publish(config, got, run_id="r1",
                                         analysis_type="dummy", title="x"))
    assert env["params"]["analysis"] == {"horizon": 7, "damping": 0.85}
    assert env["params"]["envelope"]["state_dict_version"] == "sd_abc"


def test_publishing_different_parameters_under_the_same_title_is_refused(config):
    """id 는 (run_id, analysis_type, title) 로만 정해진다 — 파라미터는 안 들어간다.

    그래서 제목이 같으면 다른 파라미터의 결과가 조용히 덮어써진다. 발행물 하나가
    두 계산을 가리키게 되므로 막는다.
    """
    first = get_analysis("dummy_with_knobs")(_cubes(), horizon=3)
    second = get_analysis("dummy_with_knobs")(_cubes(), horizon=9)
    publish(config, first, run_id="r1", analysis_type="dummy", title="같은 제목")
    with pytest.raises(ConflictingPublicationError, match="horizon"):
        publish(config, second, run_id="r1", analysis_type="dummy", title="같은 제목")


@analysis("dummy_with_a_set")
def _dummy_with_a_set(cubes, holidays: set[str] | None = None, **_):
    return AnalysisResult(frame=pd.DataFrame({"x": [1]}), headline={},
                          envelope=FULL_ENVELOPE)


def test_a_set_parameter_is_recorded_in_a_stable_order():
    """집합의 `repr` 순서는 프로세스마다 다르다(문자열 해시가 무작위화된다).

    그대로 기록하면 같은 호출이 실행마다 다른 파라미터로 남고, 재발행이 거짓 충돌로
    거부된다. 정렬해 담는다.
    """
    got = get_analysis("dummy_with_a_set")(_cubes(), holidays={"2026-08-15",
                                                              "2026-01-01"})
    assert got.params["holidays"] == ["2026-01-01", "2026-08-15"]


def test_republishing_a_call_with_a_set_parameter_is_not_a_conflict(config):
    holidays = {"2026-01-01", "2026-03-01", "2026-05-05", "2026-08-15"}
    got = get_analysis("dummy_with_a_set")(_cubes(), holidays=holidays)
    publish(config, got, run_id="r3", analysis_type="dummy", title="x")
    publish(config, got, run_id="r3", analysis_type="dummy", title="x")


def test_republishing_the_identical_call_is_still_idempotent(config):
    """대시보드가 같은 세그먼트를 열 번 봐도 발행물은 하나여야 한다."""
    from data_layer.results import list_results
    got = get_analysis("dummy_with_knobs")(_cubes(), horizon=3)
    publish(config, got, run_id="r2", analysis_type="dummy", title="x")
    publish(config, got, run_id="r2", analysis_type="dummy", title="x")
    assert len(list_results(config, run_id="r2")) == 1


def test_the_registry_finds_a_declared_analysis():
    @analysis("dummy_for_test")
    def _dummy(cubes, **params):
        return AnalysisResult(frame=pd.DataFrame(), headline={}, envelope={})

    assert "dummy_for_test" in list_analyses()
    assert get_analysis("dummy_for_test") is _dummy


def test_an_unknown_analysis_name_is_rejected():
    with pytest.raises(UnknownAnalysisError, match="nope"):
        get_analysis("nope")
