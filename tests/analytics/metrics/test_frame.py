import pandas as pd
import pytest

from analytics.metrics.frame import (
    AmbiguousRollupError,
    NonAdditiveMeasureError,
    additive_sum,
    full_combination_rows,
    rollup_rows,
    select_segment,
)

AXES = ("period", "os", "gender")


def _cube() -> pd.DataFrame:
    """전체 조합 2행 + os 접은 롤업 1행 + 전체 롤업 1행."""
    return pd.DataFrame([
        {"period": "2026-07-27", "os": "android", "gender": "M", "sessions": 10, "uv": 8},
        {"period": "2026-07-27", "os": "ios", "gender": "M", "sessions": 5, "uv": 4},
        {"period": "2026-07-27", "os": None, "gender": "M", "sessions": 15, "uv": 11},
        {"period": None, "os": None, "gender": None, "sessions": 15, "uv": 11},
    ])


def test_full_combination_rows_drops_every_rollup_row():
    got = full_combination_rows(_cube(), AXES)
    assert len(got) == 2
    assert set(got["os"]) == {"android", "ios"}


def test_summing_the_raw_frame_would_double_count():
    # 이 테스트는 왜 필터가 필요한지 고정한다. 원본 합계는 실제의 3배다.
    raw = _cube()["sessions"].sum()
    filtered = full_combination_rows(_cube(), AXES)["sessions"].sum()
    assert raw == 45
    assert filtered == 15


def test_rollup_rows_selects_the_row_where_the_named_axes_are_folded():
    got = rollup_rows(_cube(), AXES, folded=("os",))
    assert len(got) == 1
    assert int(got.iloc[0]["uv"]) == 11


def test_rollup_rows_can_select_the_grand_total():
    got = rollup_rows(_cube(), AXES, folded=("period", "os", "gender"))
    assert len(got) == 1
    assert int(got.iloc[0]["sessions"]) == 15


def test_rollup_rows_rejects_an_axis_that_does_not_exist():
    with pytest.raises(KeyError, match="nope"):
        rollup_rows(_cube(), AXES, folded=("nope",))


def test_additive_sum_allows_additive_measures():
    rows = full_combination_rows(_cube(), AXES)
    assert additive_sum(rows, "sessions") == 15


def test_additive_sum_refuses_uv():
    # uv 는 큐브의 롤업 행에서 읽어야 한다. 합산하면 부풀어 오른다.
    rows = full_combination_rows(_cube(), AXES)
    with pytest.raises(NonAdditiveMeasureError, match="uv"):
        additive_sum(rows, "uv")


def test_select_segment_filters_by_equality():
    got = select_segment(full_combination_rows(_cube(), AXES), os="android")
    assert len(got) == 1
    assert int(got.iloc[0]["sessions"]) == 10


def test_select_segment_accepts_a_list_of_values():
    got = select_segment(full_combination_rows(_cube(), AXES), os=["android", "ios"])
    assert len(got) == 2


def test_select_segment_rejects_an_unknown_column():
    with pytest.raises(KeyError, match="nope"):
        select_segment(_cube(), nope="x")


def test_a_cube_without_rollup_rows_passes_through_untouched():
    # 전이·품질 큐브는 평범한 GROUP BY 라 롤업 행이 없다.
    edges = pd.DataFrame([
        {"period": "2026-07-27", "os": "android", "gender": "M", "cnt": 3},
    ])
    assert len(full_combination_rows(edges, AXES)) == 1


SESSION_AXES = (
    "period", "service_type", "os", "gender", "age_band", "daypart", "app_version",
)
_SESSION_CUBES = sorted(__import__("glob").glob("cache/cubes/session/*/date=*.parquet"))


@pytest.mark.skipif(not _SESSION_CUBES, reason="빌드된 세션 큐브가 없다")
def test_on_a_real_cube_the_filtered_sum_equals_the_grand_total_row():
    """실제 롤업 구조에서 필터가 맞는지 본다.

    손으로 만든 프레임은 실제 grouping set 조합을 재현하지 못한다. 실측(하루·6서비스):
    원본 그대로 합산하면 **9.0배** 부푼다(2억 8,909만 vs 3,212만). 전체 조합 행의
    합계가 전체 롤업 행과 정확히 같아야 필터가 옳다.
    """
    df = pd.read_parquet(_SESSION_CUBES[-1])
    full = full_combination_rows(df, SESSION_AXES)
    grand = rollup_rows(df, SESSION_AXES, folded=SESSION_AXES)
    assert len(grand) == 1
    assert int(full["sessions"].sum()) == int(grand["sessions"].iloc[0])
    assert df["sessions"].sum() > full["sessions"].sum() * 2  # 롤업 행이 실제로 있다


@pytest.mark.skipif(not _SESSION_CUBES, reason="빌드된 세션 큐브가 없다")
def test_on_a_real_cube_summing_uv_overstates_it():
    # 실측 1.71배(1,642만 vs 959만). uv 를 합산하면 안 되는 이유의 실물 증거.
    df = pd.read_parquet(_SESSION_CUBES[-1])
    full = full_combination_rows(df, SESSION_AXES)
    grand = rollup_rows(df, SESSION_AXES, folded=SESSION_AXES)
    assert full["uv"].sum() > grand["uv"].iloc[0]


def test_metrics_modules_do_not_import_the_filesystem():
    """`frame`·`markov`·`descriptive` 는 순수해야 한다.

    마르코프 수식 버그는 예외를 안 던지고 그럴듯한 숫자를 낸다. 손으로 만든 작은
    큐브로 검증할 수 있어야 하고, 그러려면 DB·config 의존이 없어야 한다.
    """
    import ast
    from pathlib import Path

    banned = {"data_layer.config", "analytics.cube.store", "duckdb", "os", "pathlib"}
    checked = 0
    for name in ("frame", "markov", "descriptive"):
        path = Path("analytics/metrics") / f"{name}.py"
        if not path.exists():
            continue
        checked += 1
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                mods = {a.name for a in node.names}
            elif isinstance(node, ast.ImportFrom):
                mods = {node.module or ""}
            else:
                continue
            assert not (mods & banned), f"{name}.py imports {mods & banned}"
    assert checked >= 1, "순수성 검사가 아무 파일도 못 봤다 — 경로가 틀렸다"


def _multi_day_cube() -> pd.DataFrame:
    """두 날짜의 큐브 파일을 이어붙인 프레임. 롤업 행이 날짜마다 하나씩 있다."""
    day1 = _cube()
    day2 = _cube().assign(period=lambda d: d["period"].where(d["period"].isna(), "2026-07-28"))
    return pd.concat([day1, day2], ignore_index=True)


def test_rollup_rows_rejects_a_frame_holding_more_than_one_days_rollups():
    """날짜별 파일을 이어붙인 뒤 롤업을 읽으면 같은 롤업이 여러 개 나온다.

    눈치 못 채고 합산하면 조용히 N배가 된다. 실제로 14일치를 이어붙였다가 한 period 에
    롤업 행이 둘 나오는 걸 밟았다. 날짜별로 읽든지, 명시적으로 합치든지 골라야 한다.
    """
    with pytest.raises(AmbiguousRollupError, match="2"):
        rollup_rows(_multi_day_cube(), AXES, folded=("period", "os", "gender"))


def test_rollup_rows_is_fine_when_exactly_one_matches():
    got = rollup_rows(_cube(), AXES, folded=("period", "os", "gender"))
    assert len(got) == 1


def test_full_combination_rows_is_unaffected_by_multi_day_frames():
    # 전체 조합 행은 날짜마다 달라서 겹치지 않는다. 합산해도 안전하다.
    got = full_combination_rows(_multi_day_cube(), AXES)
    assert len(got) == 4
