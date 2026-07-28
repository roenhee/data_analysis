import pandas as pd
import pytest

from analytics.cube.state_dict import StateDict, apply_cut, load_state_dict, save_state_dict


def _counts(pairs):
    return pd.DataFrame(pairs, columns=["value", "cnt"])


def test_apply_cut_keeps_values_up_to_the_coverage_ratio():
    counts = _counts([("a", 700), ("b", 250), ("c", 50)])
    kept = apply_cut(counts, cut_ratio=0.95, min_count=0)
    assert kept == ["a", "b"]


def test_apply_cut_drops_values_below_min_count_even_inside_the_ratio():
    counts = _counts([("a", 700), ("b", 250), ("c", 50)])
    kept = apply_cut(counts, cut_ratio=0.95, min_count=300)
    assert kept == ["a"]


def test_apply_cut_returns_values_ordered_by_count_desc():
    counts = _counts([("small", 10), ("big", 990)])
    kept = apply_cut(counts, cut_ratio=1.0, min_count=0)
    assert kept == ["big", "small"]


def test_apply_cut_on_empty_input_returns_empty():
    assert apply_cut(_counts([]), cut_ratio=0.95, min_count=0) == []


def test_version_changes_when_any_kept_list_changes():
    a = StateDict(screens=["top/홈탭"], layer1=["home_main"], layer2=[],
                  app_versions=["9.5.1"], cut_ratio=0.95, min_count=10000)
    b = StateDict(screens=["top/홈탭", "top/콘텐츠탭"], layer1=["home_main"], layer2=[],
                  app_versions=["9.5.1"], cut_ratio=0.95, min_count=10000)
    assert a.version() != b.version()


def test_version_changes_when_cut_config_changes():
    a = StateDict(screens=["s"], layer1=[], layer2=[], app_versions=[],
                  cut_ratio=0.95, min_count=10000)
    b = StateDict(screens=["s"], layer1=[], layer2=[], app_versions=[],
                  cut_ratio=0.90, min_count=10000)
    assert a.version() != b.version()


def test_version_is_stable_across_equal_dicts():
    kw = dict(screens=["s"], layer1=["l"], layer2=[], app_versions=["v"],
              cut_ratio=0.95, min_count=10000)
    assert StateDict(**kw).version() == StateDict(**kw).version()


def test_load_rejects_a_file_whose_content_does_not_match_its_version(config):
    import json

    sd = StateDict(screens=["s"], layer1=[], layer2=[], app_versions=[],
                   cut_ratio=0.95, min_count=10000)
    path = save_state_dict(config, sd)
    raw = json.loads(path.read_text())
    raw["screens"] = ["tampered"]
    path.write_text(json.dumps(raw))
    with pytest.raises(ValueError, match="hashes to"):
        load_state_dict(config, sd.version())


def test_load_rejects_a_file_missing_the_cut_parameters(config):
    """빠진 컷 파라미터가 기본값으로 조용히 채워지면 큐브가 잘못 라벨링된다."""
    import json

    sd = StateDict(screens=["s"], layer1=[], layer2=[], app_versions=[],
                   cut_ratio=0.80, min_count=500)
    path = save_state_dict(config, sd)
    raw = json.loads(path.read_text())
    del raw["cut_ratio"]
    del raw["min_count"]
    path.write_text(json.dumps(raw))
    with pytest.raises(ValueError, match="hashes to"):
        load_state_dict(config, sd.version())


def test_apply_cut_keeps_a_value_whose_count_equals_min_count():
    counts = _counts([("a", 700), ("b", 300)])
    assert apply_cut(counts, cut_ratio=1.0, min_count=300) == ["a", "b"]


def test_apply_cut_with_all_zero_counts_returns_empty():
    assert apply_cut(_counts([("a", 0), ("b", 0)]), cut_ratio=0.95, min_count=0) == []


def test_save_then_load_roundtrips(config):
    sd = StateDict(screens=["top/홈탭_진입"], layer1=["home_main"], layer2=["FEED_SLOT_ISSUE"],
                   app_versions=["9.5.1", "9.5.0"], cut_ratio=0.95, min_count=10000)
    path = save_state_dict(config, sd)
    assert path.exists()
    loaded = load_state_dict(config, sd.version())
    assert loaded == sd
