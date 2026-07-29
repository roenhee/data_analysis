"""`load_cube_set` — 분석층이 받는 `CubeSet` 을 빌더가 쓴 그 키로 읽어 온다."""
import pandas as pd
import pytest

from analytics.analyses.cubes import load_cube_set
from analytics.cube.axes import CORE_AXIS_NAMES
from analytics.cube.builder import cube_key_parts
from analytics.cube.state_dict import StateDict, save_state_dict
from analytics.cube.store import write_cube
from analytics.metrics.load import IncompleteCubeError

SERVICES = ["top"]

MEASURES = {
    "session": {"sessions": [10], "uv": [8], "pv": [80], "events": [300],
                "duration_sum": [6000]},
    "transition": {"from_state": ["START"], "to_state": ["top/홈탭_진입"],
                   "cnt": [5], "dur_sum": [50.0], "dur_n": [3]},
    "quality": {"check_name": ["null_action_name"], "violated": [1], "total": [10]},
}


def _state_dict() -> StateDict:
    return StateDict(screens=["top/홈탭_진입"], layer1=["home_main"], layer2=[],
                     app_versions=["9.5.1"], cut_ratio=0.95, min_count=10000)


def _write(config, sd, cube_name: str, date: str) -> None:
    """빌더와 **같은 키 유도**로 큐브를 쓴다. 읽기가 그 키를 찾아내야 한다."""
    row = {"period": date, **{k: v[0] for k, v in MEASURES[cube_name].items()}}
    for axis in CORE_AXIS_NAMES:
        row.setdefault(axis, "MA" if axis == "service_type" else "x")
    rows = [row]
    if cube_name == "session":
        # 세션 큐브는 `GROUPING SETS` 로 만들어져 롤업 행을 함께 갖는다:
        # `(period)` 는 `session_trend` 가 `uv` 를 읽는 행이고, `()` 는 날짜까지 접은
        # 총계 행이라 `period` 가 NULL 이다.
        measures = {k: v[0] for k, v in MEASURES[cube_name].items()}
        rows.append({**{a: None for a in CORE_AXIS_NAMES}, "period": date, **measures})
        rows.append({**{a: None for a in CORE_AXIS_NAMES}, "period": None, **measures})
    write_cube(
        config, pd.DataFrame(rows), date=date,
        **cube_key_parts(cube_name, state_dict=sd, services=SERVICES,
                         source_version="sv1"),
    )


@pytest.fixture
def built(config):
    """세 큐브 × 2일을 빌더의 키로 써 둔다."""
    sd = _state_dict()
    save_state_dict(config, sd)
    for name in MEASURES:
        for date in ("2026-07-26", "2026-07-27"):
            _write(config, sd, name, date)
    return sd


def _load(config, sd, **over):
    return load_cube_set(
        config, dates=over.pop("dates", ["2026-07-26", "2026-07-27"]),
        services=SERVICES, state_dict_version=sd.version(),
        source_version="sv1", **over,
    )


def test_it_finds_the_cubes_the_builder_wrote(config, built):
    """읽기와 쓰기가 같은 캐시 키를 유도해야 한다 — 이게 어긋나면 아무것도 못 읽는다."""
    from analytics.metrics.descriptive import SESSION_AXES
    from analytics.metrics.frame import full_combination_rows

    got = _load(config, built)
    # 세션 큐브는 롤업 행이 섞여 있어 그냥 합산하면 같은 세션을 여러 번 센다.
    assert int(full_combination_rows(got.session, SESSION_AXES)["sessions"].sum()) == 20
    assert int(got.transition["cnt"].sum()) == 10
    assert int(got.quality["total"].sum()) == 20


def test_the_state_dict_version_and_service_scope_travel_with_the_cubes(config, built):
    # 서비스는 세션 큐브의 축이 될 수 없어서(세션 44.7% 가 여러 서비스에 걸침)
    # 봉투에만 있다. 큐브에서 되찾을 수 없으므로 로더가 받아 실어 준다.
    got = _load(config, built)
    assert got.state_dict_version == built.version()
    assert got.services == SERVICES


def test_present_dates_is_the_intersection_across_the_loaded_cubes(config, built):
    """한 큐브라도 없는 날짜는 그 `CubeSet` 이 답할 수 없는 날짜다."""
    for name in MEASURES:
        _write(config, built, name, "2026-07-28")
    # 전이만 07-29 가 있다 — 교집합은 07-29 를 빼야 한다.
    _write(config, built, "transition", "2026-07-29")
    got = _load(config, built,
                dates=["2026-07-26", "2026-07-27", "2026-07-28", "2026-07-29"],
                require_complete=False)
    assert got.present_dates == ["2026-07-26", "2026-07-27", "2026-07-28"]


def test_the_frames_are_cut_to_the_present_dates(config, built):
    """프레임이 봉투가 '없다'고 적은 날짜의 행을 들고 있으면 봉투가 거짓말이 된다."""
    _write(config, built, "transition", "2026-07-29")
    got = _load(config, built,
                dates=["2026-07-26", "2026-07-27", "2026-07-29"],
                require_complete=False)
    assert "2026-07-29" not in set(got.transition["period"])
    assert set(got.transition["period"]) == set(got.present_dates)


def test_the_date_cut_keeps_the_rows_that_fold_period_away(config, built):
    """날짜까지 접은 `()` 롤업 행은 `period` 가 NULL 이다.

    날짜 필터를 `isin` 으로만 걸면 그 행이 잘려 나간다 — 실측 세션 큐브에서 15일치
    15행(하루치 총계, `uv` 969만)이 사라졌다. 그게 "기간 전체 `uv` 는 롤업 행에서
    읽어라" 가 쓰는 바로 그 행이라, 잘리면 합산으로 때우게 된다.
    """
    got = _load(config, built, dates=["2026-07-26"])
    grand = got.session[got.session["period"].isna()]
    assert len(grand) == 1
    assert int(grand["uv"].iloc[0]) == 8


def test_a_partial_build_is_refused_by_default(config, built):
    with pytest.raises(IncompleteCubeError, match="2026-07-28"):
        _load(config, built, dates=["2026-07-26", "2026-07-27", "2026-07-28"])


def test_a_partial_window_can_be_loaded_deliberately(config, built):
    got = _load(config, built, dates=["2026-07-26", "2026-07-27", "2026-07-28"],
                require_complete=False)
    assert got.requested_dates == ["2026-07-26", "2026-07-27", "2026-07-28"]
    assert got.present_dates == ["2026-07-26", "2026-07-27"]


def test_the_envelope_of_a_partial_window_says_so(config, built):
    """로더가 `present_dates` 를 채우는 이유 — 봉투의 `is_complete` 가 여기서 나온다."""
    from analytics.analyses.base import get_analysis

    got = _load(config, built, dates=["2026-07-26", "2026-07-27", "2026-07-28"],
                require_complete=False)
    envelope = get_analysis("session_trend")(got).envelope
    assert envelope["is_complete"] is False
    assert envelope["missing_dates"] == ["2026-07-28"]


def test_only_the_requested_cubes_are_loaded(config, built):
    """전이만 필요한 분석이 품질 큐브의 빈 날짜 때문에 좁아질 이유가 없다."""
    _write(config, built, "transition", "2026-07-28")
    _write(config, built, "session", "2026-07-28")
    got = _load(config, built, cube_names=("transition",),
                dates=["2026-07-26", "2026-07-27", "2026-07-28"])
    assert got.session is None
    assert got.quality is None
    assert got.present_dates == ["2026-07-26", "2026-07-27", "2026-07-28"]


def test_an_unknown_cube_name_is_rejected(config, built):
    with pytest.raises(KeyError, match="nope"):
        _load(config, built, cube_names=("nope",))


def test_a_wrong_state_dict_version_does_not_quietly_read_another_cube(config, built):
    """사전이 바뀌면 캐시 키가 바뀐다. 다른 사전의 큐브를 조용히 집어오면 안 된다."""
    other = StateDict(screens=["top/다른탭"], layer1=[], layer2=[],
                      app_versions=["9.5.1"], cut_ratio=0.95, min_count=10000)
    save_state_dict(config, other)
    with pytest.raises(Exception) as caught:
        load_cube_set(config, dates=["2026-07-26"], services=SERVICES,
                      state_dict_version=other.version(), source_version="sv1")
    assert "2026-07-26" in str(caught.value) or "not built" in str(caught.value)
