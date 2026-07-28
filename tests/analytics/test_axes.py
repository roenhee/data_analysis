from analytics.cube.axes import (
    CORE_AXIS_NAMES,
    age_band_expr,
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


def test_age_band_folds_the_source_unknown_sentinel_into_unknown():
    # service_age_band 의 0 은 원천의 '연령 미상' 센티널이므로 NULL과 같은 버킷이어야 한다.
    # 나누면 축이 8개가 아니라 9개 값이 되고 unknown 필터가 과소집계한다.
    sql = age_band_expr()
    assert "= 0" in sql
    assert "'unknown'" in sql


def _by_axis(versions, **kw):
    return {s.rsplit(" AS ", 1)[1]: s for s in core_axis_selects(versions, **kw)}


def test_each_axis_select_carries_its_own_source_column():
    # 축 이름과 표현식의 짝이 어긋나도 통과하는 테스트를 막는다.
    sel = _by_axis(["9.5.1"])
    assert sel["period"].startswith("date_id")
    assert "common.service_type" in sel["service_type"]
    assert "env.os" in sel["os"]
    assert "d.gender" in sel["gender"] and "service_age_band" not in sel["gender"]
    assert "service_age_band" in sel["age_band"] and "d.gender" not in sel["age_band"]
    assert "date.daypart" in sel["daypart"]
    assert "env.app_version" in sel["app_version"]


def test_dim_alias_is_plumbed_into_both_demography_axes():
    sel = _by_axis(["9.5.1"], dim_alias="dem")
    assert "dem.gender" in sel["gender"]
    assert "dem.service_age_band" in sel["age_band"]
