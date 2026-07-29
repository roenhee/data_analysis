"""빌드된 큐브가 있으면 분석 전부를 실데이터로 돌린다. 없으면 skip.

손으로 만든 큐브는 실제 화면 이름·롤업 구조·앱 버전 롱테일을 재현하지 못한다. 이 파일이
잡아낸 것들: 앱 버전이 982개라 품질 경고가 18,973건(봉투 2.3 MB)이 되던 것, 가장 굵은
화면 쌍이 자기 자신으로 가는 자기 루프인 것, 그리고 계획서가 적어 둔 버전 비교의 부호가
실제로는 뒤집히지 않는다는 것.
"""
import glob
import os

import pandas as pd
import pytest

from analytics.analyses.base import CubeSet, get_analysis, list_analyses, publish
from analytics.analyses.operators import compare, decompose
from analytics.metrics.load import load_holidays, load_releases


def _cube_paths(kind: str, required: set[str]) -> list[str]:
    """스키마가 맞는 큐브 파일만. 캐시에는 옛 키로 만든 큐브가 남아 있다."""
    import pyarrow.parquet as pq

    out = []
    for path in glob.glob(f"cache/cubes/{kind}/*/date=*.parquet"):
        try:
            names = set(pq.ParquetFile(path).schema.names)
        except Exception:
            continue
        if required <= names:
            out.append(path)
    return sorted(out, key=os.path.getmtime)


TRANSITION = _cube_paths("transition", {"from_state", "to_state", "cnt", "dur_n",
                                        "app_version", "service_type", "period"})
SESSION = _cube_paths("session", {"sessions", "uv", "pv", "events", "duration_sum"})
QUALITY = _cube_paths("quality", {"check_name", "violated", "total"})

needs_cubes = pytest.mark.skipif(
    not (TRANSITION and SESSION and QUALITY),
    reason="빌드된 큐브가 없다 — scripts/build_cubes.py 를 먼저 돌려라",
)


def _date_of(path: str) -> str:
    return os.path.basename(path).removeprefix("date=").removesuffix(".parquet")


@pytest.fixture(scope="module")
def real_cubes() -> CubeSet:
    dates = sorted({_date_of(p) for p in TRANSITION}
                   & {_date_of(p) for p in SESSION}
                   & {_date_of(p) for p in QUALITY})
    keep = set(dates)

    def read(paths):
        return pd.concat(
            [pd.read_parquet(p) for p in paths if _date_of(p) in keep],
            ignore_index=True,
        )

    return CubeSet(
        session=read(SESSION), transition=read(TRANSITION), quality=read(QUALITY),
        state_dict_version="sd_real_cubes", services=["top"],
        requested_dates=dates, present_dates=dates,
    )


def _params_for(name: str, cubes: CubeSet) -> dict:
    """분석마다 필요한 파라미터. `reachability` 는 실제 화면 이름을 받아야 한다."""
    if name == "session_trend":
        holidays, _ = load_holidays()
        return {"holidays": holidays}
    if name == "reachability":
        edges = cubes.transition
        pairs = edges[(edges["from_state"] != edges["to_state"])
                      & ~edges["from_state"].isin(("START", "EXIT"))
                      & ~edges["to_state"].isin(("START", "EXIT"))]
        source, target = pairs.groupby(["from_state", "to_state"])["cnt"].sum().idxmax()
        return {"source": source, "target": target, "max_k": 5}
    if name == "screen_flow":
        return {"exit_within": (1, 3)}
    return {}


def _shipped_analyses() -> list[str]:
    """`analytics.analyses` 안에 정의된 분석만.

    레지스트리는 전역이고, 연산자 테스트들이 `fake_steps` 같은 가짜 분석을 이름으로
    등록한다(`compare` 가 이름으로 찾으니 등록이 필요하다). 파일 하나만 돌릴 때는 안
    보이지만 전체 스위트에서는 섞여 들어와 실큐브에 없는 컬럼을 찾는다. 모듈로 가른다 —
    새 **실제** 분석은 그대로 자동 포함된다.
    """
    return [
        name for name in list_analyses()
        if get_analysis(name).__module__.startswith("analytics.analyses.")
    ]


@pytest.fixture(scope="module")
def real_results(real_cubes) -> dict:
    """배포되는 분석을 한 번만 돌려 재사용한다."""
    return {
        name: get_analysis(name)(real_cubes, **_params_for(name, real_cubes))
        for name in _shipped_analyses()
    }


@needs_cubes
def test_the_shipped_registry_is_what_it_should_be():
    """분석이 추가·삭제되면 여기서 눈에 띈다."""
    assert _shipped_analyses() == [
        "quality_report", "reachability", "screen_communities",
        "screen_dwell_rank", "screen_flow", "session_trend",
    ]


@needs_cubes
def test_every_registered_analysis_runs_on_real_cubes(real_results):
    for name, got in real_results.items():
        assert not got.frame.empty, f"{name} 이 빈 프레임을 냈다"
        assert got.headline, f"{name} 에 headline 이 없다 — 연산자가 걸리지 않는다"
        assert all(isinstance(v, float) for v in got.headline.values()), name


@needs_cubes
def test_the_most_travelled_screen_pair_is_a_self_loop(real_cubes):
    """실측에서 가장 굵은 쌍은 `top/엠탑조회` → 자기 자신이다.

    그래서 "가장 굵은 쌍" 을 그대로 `reachability` 에 넣으면 거부당한다. 자기 루프를
    빼고 골라야 한다 — `_params_for` 가 그렇게 한다.
    """
    edges = real_cubes.transition
    screens = edges[~edges["from_state"].isin(("START", "EXIT"))
                    & ~edges["to_state"].isin(("START", "EXIT"))]
    source, target = screens.groupby(["from_state", "to_state"])["cnt"].sum().idxmax()
    assert source == target
    with pytest.raises(ValueError, match="already on"):
        get_analysis("reachability")(real_cubes, source=source, target=target)


@needs_cubes
def test_the_known_version_comparison_is_nearly_cancelled_by_composition(real_cubes):
    """실측 회귀 그물: 9.5.1 vs 9.5.0 (MA, 배포일 이후).

    **계획서가 적어 둔 "합산 음수" 는 재현되지 않았다.** 측정값은 날짜별
    +9.2/+4.5/+6.8% 에 합산 +0.71% 다 — 부호가 뒤집히는 게 아니라 구성 변화가 효과의
    90% 를 먹는다(within +7.5%, between -6.8%). 교훈은 같다: 합산 숫자만 보면
    "효과 없음" 이라고 결론낸다. 부호까지 뒤집히는 조합은 이 15일치에 없다.

    이 수치가 움직이면 데이터나 분해가 바뀐 것이므로 확인이 필요하다.
    """
    ma = real_cubes.filter(service_type="MA")
    got = compare(ma, "screen_flow", on="app_version", a="9.5.1", b="9.5.0",
                  released=load_releases())
    assert got.dates_used == ["2026-07-26", "2026-07-27", "2026-07-28"]
    assert "release" in got.date_reason

    per_day = got.per_day["delta_mean_expected_steps"]
    assert (per_day > 0.04).all() and (per_day < 0.10).all()

    pooled = got.pooled["mean_expected_steps"]
    assert 0 < pooled < per_day.min() / 5, "합산이 하루치보다 훨씬 작아야 한다"
    assert got.weight_skew > 0.5, "버전이 서로 다른 날에 몰려 있어야 한다"

    split = decompose(ma, got, by=["period"], metric="mean_expected_steps")
    assert split.within > 0.05
    assert split.between < -0.05
    assert split.within + split.between == pytest.approx(pooled, abs=1e-9)


@needs_cubes
def test_gender_comparison_is_stable_across_days(real_cubes):
    """실측: F vs M 기대 걸음 수는 15일 내내 부호가 안 바뀌고 좁은 띠에 있다.

    계획서는 -11.1%~-6.6% 로 적었지만 실측은 -26.1%~-21.0% 였다(측정 범위가 다르다).
    고정할 값은 크기가 아니라 **성질**이다 — 날짜 가중치가 거의 안 어긋나서(skew 0.009)
    합산이 날짜별과 같은 자리에 있다. 버전 비교와 정반대 상황이라 대조군이 된다.
    """
    got = compare(real_cubes, "screen_flow", on="gender", a="F", b="M")
    assert len(got.dates_used) == 15
    per_day = got.per_day["delta_mean_expected_steps"]
    assert (per_day < 0).all()
    assert per_day.max() - per_day.min() < 0.10, "띠가 좁아야 한다"
    assert got.weight_skew < 0.05, "성별은 날짜에 고루 퍼져 있다"
    assert got.pooled["mean_expected_steps"] == pytest.approx(per_day.mean(), abs=0.05)


@needs_cubes
def test_every_published_result_carries_a_complete_envelope(config, real_results):
    from data_layer.results import read_result

    for name, got in real_results.items():
        result_id = publish(config, got, run_id="real", analysis_type=name,
                            title=f"{name} on real cubes")
        frame, envelope = read_result(config, result_id)
        assert len(frame) == len(got.frame)
        assert envelope["params"]["envelope"]["state_dict_version"] == "sd_real_cubes"
        assert envelope["caveats"]


@needs_cubes
def test_the_quality_envelope_stays_small_enough_to_publish(real_results):
    """앱 버전이 982개라 접지 않으면 경고가 18,973건 · 봉투 JSON 2.3 MB 가 된다."""
    import json

    warnings = real_results["quality_report"].envelope["warnings"]
    assert len(warnings) < 100, f"{len(warnings)}건 — 접히지 않았다"
    assert len(json.dumps(warnings)) < 100_000
    # 분모 없이 100% 를 읽으면 롱테일 버전을 주력 버전으로 오해한다.
    assert all("worst_total" in w for w in warnings)
