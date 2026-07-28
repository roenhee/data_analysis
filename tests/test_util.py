def test_package_exports():
    import data_layer

    for name in ("Config", "get_events", "run", "SourceDef"):
        assert hasattr(data_layer, name)


from data_layer.util import content_hash, day_strings


def test_content_hash_is_stable_and_order_independent():
    a = content_hash("q", {"x": 1, "y": 2})
    b = content_hash("q", {"y": 2, "x": 1})
    assert a == b
    assert isinstance(a, str) and len(a) == 16


def test_content_hash_changes_with_input():
    assert content_hash("q", 1) != content_hash("q", 2)


def test_day_strings_inclusive():
    assert day_strings("2026-01-05", "2026-01-07") == [
        "2026-01-05",
        "2026-01-06",
        "2026-01-07",
    ]


def test_day_strings_single_day():
    assert day_strings("2026-01-05", "2026-01-05") == ["2026-01-05"]


def test_day_strings_rejects_reversed_range():
    import pytest

    with pytest.raises(ValueError):
        day_strings("2026-01-07", "2026-01-05")
