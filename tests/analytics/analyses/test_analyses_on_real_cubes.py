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


# 분석이 어느 큐브를 필요로 하는가. 이 픽스처는 **화면층 세 개만** 읽는다 — 행동층 큐브는
# 15일 중 일부만 빌드돼 있어서, 넣으면 날짜 교집합이 좁아져 15일 회귀 그물이 전부 깨진다.
# 그래서 행동층 분석은 여기서 건너뛰고 아래 테스트가 **무엇이 건너뛰어졌는지** 고정한다 —
# 화면층 분석이 이 이유로 조용히 빠지면 그 테스트가 실패한다.
ACTION_LAYER_REQUIRES = {
    "click_distribution": "action",
    "conditional_flow": "cond_transition",
    "path_ranking": "path",
    "markov_order_test": "path",
}


def _runnable(name: str, cubes: CubeSet) -> bool:
    need = ACTION_LAYER_REQUIRES.get(name)
    return need is None or getattr(cubes, need) is not None


@pytest.fixture(scope="module")
def real_results(real_cubes) -> dict:
    """배포되는 분석을 한 번만 돌려 재사용한다. 큐브가 없는 분석은 건너뛴다."""
    return {
        name: get_analysis(name)(real_cubes, **_params_for(name, real_cubes))
        for name in _shipped_analyses()
        if _runnable(name, real_cubes)
    }


@needs_cubes
def test_only_the_action_layer_analyses_are_skipped(real_cubes, real_results):
    """화면층 분석이 큐브 없음으로 조용히 빠지면 여기서 걸린다."""
    skipped = [n for n in _shipped_analyses() if n not in real_results]
    assert set(skipped) <= set(ACTION_LAYER_REQUIRES), skipped


@needs_cubes
def test_the_shipped_registry_is_what_it_should_be():
    """분석이 추가·삭제되면 여기서 눈에 띈다."""
    assert _shipped_analyses() == [
        "click_distribution", "conditional_flow", "cross_service_flow",
        "markov_order_test", "path_ranking", "quality_report", "reachability",
        "screen_communities", "screen_dwell_rank", "screen_flow",
        "screen_pair_affinity", "screen_transition", "session_trend",
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
def test_quality_warnings_are_backed_by_volume_not_the_long_tail(real_results):
    """버전(실측 982개)을 접지 않으면 경고 18,973건 · 봉투 2.3 MB 이고, 전부 세션 몇
    건짜리 버전의 100% 였다. 접은 뒤에는 18건이고 전부 물량이 뒷받침한다.
    """
    import json

    from analytics.cube.sql import QUALITY_CHECKS

    warnings = real_results["quality_report"].envelope["warnings"]
    assert len(warnings) < 100, f"{len(warnings)}건 — 집계 수준이 잘못됐다"
    assert len(json.dumps(warnings)) < 100_000

    # 봉투의 경고 목록은 **모양이 섞여 있다.** 분석이 낸 것 말고도 `envelope_for` 가
    # 자동으로 붙이는 것들이 있다(`screens_lumped_into_other`). 여기서 고정하려는 것은
    # 품질 검사 경고의 모양이므로 그 이름들로 좁힌다.
    checks = [w for w in warnings if w["check_name"] in QUALITY_CHECKS]
    assert checks, "품질 검사 경고가 하나는 있어야 한다"
    assert all({"period", "ratio", "total"} <= set(w) for w in checks)
    # 롱테일의 100% 가 사라졌다는 뜻: 비율 1.0 짜리는 전부 대형이다.
    assert not [w for w in checks if w["ratio"] >= 1.0 and w["total"] < 1000]


@needs_cubes
def test_the_search_dwell_gap_surfaces_as_the_loudest_warning(real_cubes, real_results):
    """실측: `search` 는 체류가 15일 내내 100% 미측정이다(3억 6,754만 화면 방문).

    이건 코드베이스가 이미 아는 사실("search 0%")인데, 버전 단위로 경고할 때는 세션
    3건짜리 100% 뒤에 묻혀 있었다. 집계 수준을 맞추면 가장 큰 항목이 된다.
    """
    warnings = real_results["quality_report"].envelope["warnings"]
    search = [w for w in warnings if w["check_name"] == "screen_without_dwell"
              and w["service_code"] == "search"]
    assert len(search) == len(real_cubes.present_dates)
    assert all(w["ratio"] == pytest.approx(1.0) for w in search)
    assert all(w["total"] > 1_000_000 for w in search)


@needs_cubes
def test_the_pooled_rate_would_hide_the_service_that_is_bad(real_cubes, real_results):
    """서비스를 합치면 `session_no_screen` 이 어떤 임계치에도 안 걸린다.

    실측 (서비스,날짜) 수준은 이분돼 있다 — top 0.1960~0.3262, 나머지 5서비스
    0.0087~0.0780. 합치면 0.22 다. 그래서 서비스는 접지 않는다.
    """
    got = real_results["quality_report"]
    fired = [w for w in got.envelope["warnings"]
             if w["check_name"] == "session_no_screen"]
    assert {w["service_code"] for w in fired} == {"top"}
    # 상시 표시다 — 정상 변동의 상위 몇 일만이 아니라 매일 걸려야 한다.
    assert len(fired) == len(real_cubes.present_dates)
    assert all(w["ratio"] > 0.15 and w["total"] > 1_000_000 for w in fired)


@needs_cubes
def test_the_pooled_flow_headline_sits_outside_every_service(real_cubes):
    """A5 를 하게 만든 사실. 합산 기대 화면 수가 여섯 서비스 전부보다 크다.

    실측: 합산 **10.62** 대 서비스별 2.77(content_v)~8.08(top). 이탈확률은 반대로 합산
    **0.0975** 가 최소 0.1407 보다 **낮다** — 벗어나는 방향이 위쪽만이 아니다. 화면 간
    전이의 49.68%가 서비스를 건너뛰어서, 합친 체인에는 어떤 단일 서비스 안에도 없는
    전이가 있다. 고정할 것은 크기가 아니라 **합산이 범위 밖이라는 사실**이다.
    """
    from analytics.analyses.operators import per_service

    got = per_service(real_cubes, "screen_flow")
    assert got.services == ["content_v", "entertain", "media", "search", "sports",
                            "top"]
    steps_lo, steps_hi = got.outside_range["mean_expected_steps"]
    assert got.pooled["mean_expected_steps"] > steps_hi
    exit_lo, _ = got.outside_range["mean_exit_prob"]
    assert got.pooled["mean_exit_prob"] < exit_lo
    assert 0.45 < got.cross_service_share < 0.55


@needs_cubes
def test_the_dictionary_starves_the_small_services(real_results):
    """마르코프 노트북이 재던 `OTHER` 누출. 파이프라인이 잃었다가 되살렸다.

    사전 채택 컷이 **전체 물량** 누적 95%라 top 이 물량의 56%를 차지하면서 작은 서비스가
    먼저 잘린다. 전체로는 4.71%인데 서비스별로는 sports **36.97%** · entertain
    **18.67%** · top 3.05% · media 0.52% · content_v 0.003% · search 0% 다.

    `/other` 는 드문 화면이 아니라 138개 이름을 접은 가짜 화면이다. 상태를 합치는 것은
    합쳐진 화면들의 나가는 분포가 같을 때만 무손실이므로, sports 의 기대 화면 수 5.32 는
    상태 둘 중 하나가 그 버킷인 체인의 값이다. **전체 한 숫자로는 그게 안 보인다.**
    """
    got = real_results["screen_flow"]
    shares = got.envelope["other_share"]
    assert shares["sports"] > 0.30 and shares["entertain"] > 0.15
    assert shares["media"] < 0.02 and shares["search"] == pytest.approx(0.0)
    assert 0.04 < sum(
        shares[s] * got.envelope["service_mix"][s] for s in shares
    ) < 0.06, "전체 비중은 95% 컷이 약속한 5% 근처여야 한다"

    # 상시 표시다 — 임계치가 나쁜 무리 최솟값 아래라 그 둘만 매일 걸린다.
    fired = {w["service_code"] for w in got.envelope["warnings"]
             if w["check_name"] == "screens_lumped_into_other"}
    assert fired == {"sports", "entertain"}


@needs_cubes
def test_a_simple_weighted_average_is_not_flagged_as_outside_the_range(real_cubes):
    """`outside_range` 는 무조건 울리는 경보가 아니다.

    `screen_dwell_rank` 의 방문당 체류는 물량 가중 평균이라 **반드시** 서비스별 범위
    안이다(실측 합산 48.42, 서비스별 35.69~73.29). 그래서 `screen_flow` 가 걸리는 것은
    체인 길이라는 지표의 성질이고 분해 자체의 부작용이 아니다.
    """
    from analytics.analyses.operators import per_service

    assert per_service(real_cubes, "screen_dwell_rank").outside_range == {}


@needs_cubes
def test_the_service_mix_shows_the_pooled_number_is_mostly_top(real_results):
    """실측 top 61.8% 대 content_v 2.1%. 봉투에 없으면 합산이 "앱 전체" 로 읽힌다."""
    mix = real_results["screen_flow"].envelope["service_mix"]
    assert set(mix) == {"top", "media", "entertain", "sports", "content_v", "search"}
    assert mix["top"] > 0.55
    assert sum(mix.values()) == pytest.approx(1.0)


@needs_cubes
def test_exit_lift_is_visit_weighted_normalized_to_one(real_results):
    """`exit_lift` = 화면 이탈률 / 방문 가중 평균 이탈률(baseline, 노트북 `lift_exit`).

    baseline 은 모든 화면에 같은 상수(방문 가중 평균 이탈률)라야 한다. 방문 가중으로
    `exit_lift` 를 다시 평균하면 baseline 이 곧 그 평균이므로 정확히 1이어야 하고,
    어느 화면은 평균보다 더 자주 떠나야(`exit_lift > 1`) 이 지표가 뜻이 있다 — 전부
    1 근처면 baseline 과 다를 게 없다.
    """
    frame = real_results["screen_flow"].frame
    assert {"exit_baseline", "exit_lift"} <= set(frame.columns)

    assert frame["exit_baseline"].nunique() == 1, "baseline 은 화면마다 같은 상수여야 한다"
    baseline = float(frame["exit_baseline"].iloc[0])
    assert baseline == pytest.approx(
        real_results["screen_flow"].headline["mean_exit_prob"]
    )
    assert (frame["exit_lift"] > 1).any(), "평균보다 더 자주 떠나는 화면이 하나는 있어야 한다"

    weights = frame["visits"] / frame["visits"].sum()
    assert (frame["exit_lift"] * weights).sum() == pytest.approx(1.0)


@needs_cubes
def test_cross_service_movement_is_about_half_of_screen_transitions(real_results):
    """감춰져 있던 절반. `screen_flow` 는 화면 단위라 이걸 못 보여준다.

    실측 `cross_service_share` 0.4968, `switch_entropy` 2.2204 nats. 건너뛰는 쌍이
    30개라 최대 엔트로피가 ln(30)=3.40 이므로 65% 수준 — 한 경로로 몰리는 게 아니라
    여러 방향으로 흩어진다.
    """
    got = real_results["cross_service_flow"]
    assert 0.45 < got.headline["cross_service_share"] < 0.55
    assert 2.0 < got.headline["switch_entropy"] < 2.5
    assert got.frame["cnt"].is_monotonic_decreasing
    assert set(got.frame["from_service"]) == {"top", "media", "entertain", "sports",
                                              "content_v", "search"}


@needs_cubes
def test_the_smaller_services_send_most_of_their_traffic_to_top(real_results):
    """실측에서 처음 드러난 것: 작은 서비스들은 top 으로 흘러간다.

    출발지 대비 비중으로 media→top **71.7%**, content_v→top **75.4%**,
    entertain→top 62.2%, sports→top 59.8% 다. top 은 60.3% 를 자기 안에 두고
    search 는 59.6% 가 자기 자신(화면이 하나뿐이라 자기 루프)이다.

    합산 지표에서는 이게 안 보인다 — `screen_flow` 는 화면 단위이고 `per_service` 는
    이 전이를 버린다.
    """
    frame = real_results["cross_service_flow"].frame.set_index(
        ["from_service", "to_service"]
    )
    for service in ("media", "content_v", "entertain", "sports"):
        assert frame.loc[(service, "top"), "share_of_origin"] > 0.55, service
    assert frame.loc[("top", "top"), "share_of_origin"] > 0.55


@needs_cubes
def test_the_session_cube_is_additive_except_uv(real_cubes):
    """`session_trend` 의 슬라이스 fallback 이 서 있는 바닥. 실큐브로 직접 검산한다.

    전체 조합 행을 합한 값이 `(period)` 롤업 행과 **부동소수 정밀도까지** 같아야
    가산이라고 말할 수 있다. 실측 15일 전부 배율 1.000000 이다 —
    `sessions`·`pv`·`events`·`duration_sum`. `uv` 만 1.68~1.76배로 부푼다(같은 사람이
    여러 칸에 들어가므로). 그래서 fallback 은 넷을 합하고 `uv` 는 NaN 으로 둔다.
    """
    from analytics.metrics.descriptive import SESSION_AXES
    from analytics.metrics.frame import full_combination_rows, rollup_rows

    session = real_cubes.session
    folded = tuple(a for a in SESSION_AXES if a != "period")
    uv_ratios = []
    for day in real_cubes.present_dates:
        one = session[session["period"] == day]
        roll = rollup_rows(one, SESSION_AXES, folded=folded).iloc[0]
        full = full_combination_rows(one, SESSION_AXES)
        for measure in ("sessions", "pv", "events", "duration_sum"):
            assert float(full[measure].sum()) == float(roll[measure]), (day, measure)
        uv_ratios.append(float(full["uv"].sum()) / float(roll["uv"]))
    assert min(uv_ratios) > 1.65 and max(uv_ratios) < 1.80


@needs_cubes
def test_the_rollup_rows_would_inflate_the_stratum_volume_eightfold(real_cubes):
    """롤업 행을 함께 세면 하루 프레임에서 물량이 **정확히 8배**가 된다.

    손으로 만든 픽스처는 접은 축이 하나라 2배였다. 실큐브는 grouping set 이 8개다 —
    `decompose` 가 표에 싣는 `a_cnt` 는 사람이 읽는 절대 물량이라 8배로 실리면 안 된다.

    15일치를 이어붙인 프레임은 9.0배다(파일마다 날짜까지 접은 `()` 행이 하나 더 있어
    period NULL 행이 15개 된다). 그래서 하루로 잘라 재는 이 테스트가 8을 본다.
    """
    from analytics.metrics.descriptive import SESSION_AXES
    from analytics.metrics.frame import full_combination_rows

    one = real_cubes.session
    one = one[one["period"] == real_cubes.present_dates[-1]]
    full = full_combination_rows(one, SESSION_AXES)
    assert float(one["sessions"].sum()) / float(full["sessions"].sum()) == 8.0


@needs_cubes
def test_the_session_cube_version_comparison_moves_opposite_to_the_flow_one(real_cubes):
    """실측 회귀 그물 — 세션 큐브에서 처음 물어본 질문이다: 9.5.1 에서 체류가 올랐나.

    **내려갔다.** 세션당 체류는 합산 −18.8%, 날짜별 −43.7/−11.5/−7.2% 로 사흘 다 음수다.
    같은 두 버전의 기대 걸음 수는 +4~7% 였다(위 `screen_flow` 테스트) — **두 지표가
    반대로 움직인다.** 9.5.1 세션은 화면을 더 많이 밟으면서 더 짧게 머문다.

    다만 이 비교는 그대로 읽으면 안 된다: `weight_skew` 0.51 이고, `within` −28.0% 는
    거의 전부 07-26 에서 온다 — 그날 9.5.1 은 56만 세션, 9.5.0 은 1,440만으로 25:1 이라
    배포일 컷오프를 지나고도 램프업 첫날의 소수 집단을 재고 있다. 고정할 것은 크기가
    아니라 **부호와 그 취약함**이다.
    """
    ma = real_cubes.filter(service_type="MA")
    got = compare(ma, "session_trend", on="app_version", a="9.5.1", b="9.5.0",
                  released=load_releases())
    assert got.dates_used == ["2026-07-26", "2026-07-27", "2026-07-28"]

    per_day = got.per_day["delta_seconds_per_session"]
    assert (per_day < 0).all(), "사흘 다 체류가 내려갔다"
    pooled = got.pooled["seconds_per_session"]
    assert per_day.min() < pooled < per_day.max()
    assert got.weight_skew > 0.5, "버전이 서로 다른 날에 몰려 있어야 한다"

    split = decompose(ma, got, by=["period"], metric="seconds_per_session")
    assert split.within < pooled < 0, "구성 변화가 델타를 완화하는 쪽으로 작용한다"
    assert split.between > 0
    assert split.within + split.between == pytest.approx(pooled, abs=1e-9)

    # 램프업 첫날의 물량 불균형이 `within` 을 끌고 간다 — 그게 이 비교의 약점이다.
    ramp = split.per_stratum.set_index("period").loc["2026-07-26"]
    assert ramp["b_cnt"] / ramp["a_cnt"] > 20


@needs_cubes
def test_the_busiest_pair_is_not_the_most_affine_one(real_results):
    """PMI 가 따로 있어야 하는 이유가 실측에 그대로 있다.

    카운트 1위는 `top/엠탑조회` 자기 루프(3억 120만)인데 PMI 로는 251쌍 중 **47위**
    (0.397)다. PMI 1위는 관측 263건짜리 `content_v/other` 자기 루프(12.16)다 — 얇은
    셀의 PMI 가 가장 크게 튄다는 경고가 `cnt` 열과 함께 봉투에 있는 이유다.

    상호정보량은 0.641 nats — "현재 화면을 알면 다음 화면을 얼마나 아는가" 이고,
    쌍마다 다른 PMI 와 달리 세그먼트끼리 견줄 수 있는 스칼라다.
    """
    got = real_results["screen_pair_affinity"]
    assert 0.60 < got.headline["mutual_information"] < 0.70
    assert 240 <= got.headline["pairs"] <= 260

    frame = got.frame
    assert frame["pmi"].is_monotonic_decreasing
    busiest = frame["cnt"].idxmax()
    assert frame.loc[busiest, "from_state"] == frame.loc[busiest, "to_state"]
    assert busiest > 20, "카운트 1위가 PMI 상위권이면 이 지표는 빈도의 재탕이다"
    # PMI 1위는 얇은 셀이다 — 임계치로 막지 않고 `cnt` 를 함께 내는 근거.
    assert frame.loc[0, "cnt"] < 10_000

    # 커버리지는 비어 있다 — 카운트만 쓰므로 부분 측정 문제가 없다.
    assert got.envelope["coverage"] == {}
    thin = [w for w in got.envelope["warnings"]
            if w["check_name"] == "thin_transition_cells"]
    assert len(thin) == 1 and thin[0]["share"] == pytest.approx(0.189, abs=0.01)


@needs_cubes
def test_a_version_slice_reports_uv_as_unavailable_on_real_cubes(real_cubes):
    """실큐브에서도 슬라이스는 `uv` 를 못 읽는다 — 0 이 아니라 NaN 이고 봉투가 말한다."""
    got = get_analysis("session_trend")(
        real_cubes.filter(service_type="MA", app_version="9.5.1")
    )
    assert got.frame["uv"].isna().all()
    assert got.frame["sessions_per_user"].isna().all()
    names = [w["check_name"] for w in got.envelope["warnings"]]
    assert "uv_unavailable_for_this_slice" in names
    # 이 슬라이스도 사전 커버리지가 나쁜 서비스를 물고 있다 — 봉투가 둘 다 말한다.
    assert "screens_lumped_into_other" in names
    # 가산 측정값은 그대로 나온다 — 슬라이스라고 분석이 죽지 않는다.
    assert got.headline["sessions"] > 1_000_000
    assert 100 < got.headline["seconds_per_session"] < 600
