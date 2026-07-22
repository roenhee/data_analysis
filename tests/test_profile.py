import pandas as pd

from data_layer.profile import build_dictionary, compute_dictionary


def _counts():
    # 누적: A=0.5, B=0.8, C=0.95, D=1.0
    return pd.DataFrame(
        {"action_name": ["A", "B", "C", "D"], "cnt": [50, 30, 15, 5]}
    )


def test_compute_dictionary_cutoff_marks_vocabulary():
    d = compute_dictionary(_counts(), cutoff=0.8)
    assert "A" in d["vocabulary"]
    assert "B" in d["vocabulary"]
    assert "C" in d["vocabulary"]  # 경계를 넘기는 첫 항목까지 포함
    assert "D" not in d["vocabulary"]
    assert d["cutoff"] == 0.8


def test_compute_dictionary_maps_nonvocab_to_other():
    d = compute_dictionary(_counts(), cutoff=0.8)
    assert d["mapping"]["A"] == "A"
    assert d["mapping"]["D"] == "other"


def test_compute_dictionary_applies_rules():
    rules = {"A": "HOME"}
    d = compute_dictionary(_counts(), cutoff=1.0, mapping_rules=rules)
    assert d["mapping"]["A"] == "HOME"
    assert d["mapping"]["B"] == "B"


def test_build_dictionary_uses_injected_counts_fetcher():
    called = {}

    def fake_counts(source, window):
        called["window"] = window
        return _counts()

    d = build_dictionary(
        source=object(),
        window=("2026-01-05", "2026-02-01"),
        cutoff=0.8,
        counts_fetcher=fake_counts,
    )
    assert called["window"] == ("2026-01-05", "2026-02-01")
    assert d["cutoff"] == 0.8
    assert "vocabulary" in d
