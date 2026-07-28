from analytics.cube.axes import (
    CORE_AXIS_NAMES,
    app_version_expr,
    core_axis_selects,
    os_expr,
)


def test_core_axis_names_are_the_seven_from_the_spec():
    assert CORE_AXIS_NAMES == (
        "period",
        "service_type",
        "os",
        "gender",
        "age_band",
        "daypart",
        "app_version",
    )


def test_os_expr_buckets_known_families_and_folds_the_rest():
    sql = os_expr()
    for family in ("android", "ios", "windows", "macos"):
        assert f"'{family}'" in sql
    assert "'other'" in sql
    # 실측된 os 값은 소문자다
    assert "lower(" in sql


def test_app_version_expr_keeps_listed_versions_and_folds_others():
    sql = app_version_expr(["9.5.1", "9.5.0"])
    assert "'9.5.1'" in sql
    assert "'9.5.0'" in sql
    assert "'other'" in sql


def test_app_version_expr_escapes_single_quotes():
    sql = app_version_expr(["9.5'1"])
    assert "9.5''1" in sql


def test_app_version_expr_with_no_versions_is_all_other():
    sql = app_version_expr([])
    assert sql.strip() == "'other'"


def test_core_axis_selects_emits_one_alias_per_axis_in_order():
    selects = core_axis_selects(["9.5.1"])
    assert len(selects) == len(CORE_AXIS_NAMES)
    for sel, name in zip(selects, CORE_AXIS_NAMES):
        assert sel.endswith(f" AS {name}")


def test_unmatched_demography_becomes_unknown_not_null():
    selects = core_axis_selects(["9.5.1"])
    gender = next(s for s in selects if s.endswith(" AS gender"))
    age = next(s for s in selects if s.endswith(" AS age_band"))
    assert "'unknown'" in gender
    assert "'unknown'" in age
