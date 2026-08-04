# 대조: 마르코프 노트북의 분석값 ↔ 현재 분석층

**날짜:** 2026-07-30 · **대상:** `~/Desktop/리서치/markov/markov_analysis.ipynb` 와 그
산출 CSV 8종 · **현재:** 분석 8개 + 연산자 3개 (`analytics/analyses/`)

**결론:** 마르코프 지표 본체는 **컬럼 이름까지 일치**한다. 안 맞는 곳이 넷이고, 그중 하나는
같은 이름의 분석이 **다른 그래프**를 보고 있다.

> **2026-07-30 결정: 이 격차 넷을 지금 좇지 않는다.** 4단계 대시보드까지 만들어 전체 분석을
> 한 번 뽑아 본 뒤에 스킬을 추가·변경·유지 중 무엇을 할지 정한다(사용자 판단). 이 문서는
> 그때 쓸 근거로 남긴다 — 근거 없이 "나중에 결정" 하면 결정할 수 없다.

## 일치하는 것

| 노트북 산출물 | 현재 |
|---|---|
| `expected_steps_to_end.csv` (99행) — `expected_steps_to_end`·`exit_p` | `screen_flow` → `expected_steps`·`exit_prob` |
| `kstep-exit-state_k5.csv` — `p_exit_within_5` | `screen_flow(exit_within=(5,))` → `p_exit_within_5` |
| `entorpy_state_transition_metrics_top100_minout1000.csv` (196행) — `entropy`·`hhi`·`top_p`·`effective_choices`·`out_degree`·`top_to` | `screen_flow` (`metrics.markov.determinism`) — **컬럼명까지 같다** |
| `action_name_cnt.csv` (10,001행) | state 사전 채택 입력(`state_sql.build_screen_count_sql`) |

노트북의 채택 컷 `cutoff_ratio = 0.95` 도 그대로 왔다. 나머지는 다르다 —
`2026-07-30-screen-namespace.md` 아래의 "노트북과 뭐가 다른가" 표 참고
(서비스 접두어, Pageview 한정, `min_count` 추가, 서비스별 `/other` 버킷).

## 안 맞는 곳 넷

### ① 이탈 baseline 대비 lift가 없다 — **작다**

노트북 `exti_prob.csv` (188행)는 `exit_p` 옆에 `p_end_baseline`·`lift_exit`·`delta_exit` 를
낸다. 실측 예: `앱종료` 화면의 이탈확률 **0.5627** 이 전체 baseline **0.05559** 의
**10.12배**(`delta_exit` +0.5071).

현재 `screen_flow` 는 `exit_prob` 절대값만 낸다. 무엇에 비해 높은지는 소비자가 직접
계산해야 하고, 그러면 baseline 정의가 사람마다 갈린다.

**작업 크기:** `screen_flow` 프레임에 두 열 추가. baseline 을 무엇으로 할지(방문 가중 전체
이탈확률 = 현재 `mean_exit_prob`)만 정하면 된다.

### ② hub 이웃 목록이 모양이 다르다 — **중간**

노트북 `hub_edges_longform.csv` (7,704행)는 허브 화면마다 `direction` (IN/OUT) × `rank` ×
`other_state` × `share` 를 낸다 — "이 화면으로 **들어오는** 상위 이웃과 그 비중".

`screen_pair_affinity` 는 모든 쌍의 PMI + `cnt` 를 내지만 **다른 질문에 답한다**: PMI 는
"독립 가정보다 얼마나 자주 일어나나" 이고 hub 목록은 "실제로 어디서 오나" 다. 전이 큐브에서
파생 가능하지만 이름 붙은 분석이 없어 **발행되지 않는다.**

**작업 크기:** 새 분석 하나(`screen_neighbors` 같은). 프레임이 화면 한 줄이 아니라
(화면, 방향, 순위) 라 `screen_flow` 에 못 들어간다 — `screen_pair_affinity` 와 같은 이유다.

### ③ 군집: 그래프 원천은 **같다(1-step)**. 다른 건 필터·resolution·출력이다 — **중간**

> **2026-08-04 정정.** 아래 원래 표(취소선)는 파일명 `top5gram10` 을 "그래프를 5-gram
> 엣지로 만들었다" 로 잘못 읽은 것이다. 노트북 셀(`markov_analysis.ipynb`, Louvain 셀)을
> 직접 열어 확인하니 **군집 그래프 G 는 1-step 전이를 대칭화해서 만든다** — 현재
> `screen_communities._screen_graph` 와 같은 원천이다. `top5gram10` 은 그래프가 아니라
> **출력 설정**이다: 각 군집마다 "5개 상태가 모두 그 군집에 속하는 5-gram" 상위 10개를
> 뽑는 표(`*_comm_top5.csv`). 노트북은 군집 **네트워크 그래프를 그리지 않았다**(nx.draw·
> pyvis 없음, CSV 3종만).

노트북 파일명이 스스로 파라미터를 적고 있다:
`community_excl_lifecycle_r1.2_top5gram10_*`

| | 노트북 | 현재 `screen_communities` |
|---|---|---|
| 그래프 원천 | **1-step 전이 대칭화** (`transition_count` 테이블) | **1-step 전이 대칭화** — 같다 |
| resolution | **1.2** | 기본 **1.0** (파라미터로 바꿀 수 있다) |
| 자기 루프 | 제외 (`from_state <> to_state`) | **포함** |
| 제외 상태 | `{__START__, __END__, 앱종료, 앱실행_포그라운드, 앱시작_링크, OTHER, ETC, UNKNOWN}` | `START`·`EXIT` 만 (`*/other` 는 남긴다) |
| ~~그래프 원천~~ | ~~5-gram 상위 엣지 (`top5gram10`)~~ | ~~1-step 전이~~ |

남은 차이는 **파라미터·필터 수준**이지 다른 그래프가 아니다: resolution(파라미터로 이미
조정 가능), 자기 루프 포함 여부, `*/other`·생애주기 상태 제외 범위. "군집 수를 강한 사실로
읽지 말 것"(화면 15개, modularity 0.394, 노드 순서로 3개↔4개)은 이 필터들과 무관하게 유효하다.

**진짜 격차는 "군집별 대표 5-gram 경로 표"다.** 노트북의 `*_comm_top5.csv` (community_id ×
rank × path × cnt × support_in_comm)는 "이 군집에서 사람들이 실제로 밟는 5-단계 경로"를 낸다.
`path` 큐브 n=5 + `screen_communities` 의 상태→군집 매핑을 조인하면 만들 수 있다(모든 5개
상태가 같은 군집일 때만). 이게 사용자가 "5-gram" 으로 기억하는 산출물이다 — 새 분석
`community_paths` 로 발행한다. (대시보드가 군집을 색칠 네트워크 그래프로 그리는 것은 노트북에
없던 **추가 기능**이지 파리티가 아니다.)

### ④ 체류 십분위 × 다음 화면이 없다 — **재빌드 필요**

노트북 `home_duration_csv/home_duration_nextstate_by_decile_top5_minn2000.csv` 는
홈 체류를 십분위로 나누고 각 십분위의 다음 화면 분포를 낸다. 실측 D01(가장 짧게 머문 10%):
**30.4% 앱종료**, 14.3% search.

**지금 구조로 불가능하다.** 전이 큐브에 셀별 `dur_sum`·`dur_n` 은 있지만 십분위를 만들려면
**방문 단위 체류 분포**가 필요한데 큐브가 이미 합쳐 버렸다. 체류 십분위를 큐브 축으로 넣어
다시 빌드해야 한다 — `sql_hash` 가 바뀌어 전이 큐브 전량 재빌드다.

`D-2`(고차 마르코프)가 "큐브가 시퀀스를 집계해 버려 지금 구조로 불가"인 것과 같은 종류의
한계이고, 같은 해법(시퀀스 또는 방문 단위 캐시)이 필요하다.

## 반대 방향 — 현재만 있는 것

노트북에 없던 것도 기록해 둔다. 격차를 메우는 판단을 할 때 이쪽 비용도 같이 봐야 한다.

- **세그먼트 비교 가드** — `compare` 의 날짜 겹침 강제·배포일 컷오프. 노트북에는 없었고,
  없으면 버전 델타가 달력을 잰다(실측 +2.9% vs −0.2%, 부호까지 갈림)
- **구성 분해** `decompose` — 심슨의 역설을 `within`/`between` 으로 가른다
- **서비스별 분해** `per_service` — 합산이 서비스 범위 밖인지 자동 표시
- **서비스 간 이동** `cross_service_flow` — 화면 간 전이의 49.68%
- **상호정보량** — 쌍마다 다른 PMI 와 달리 세그먼트끼리 견줄 수 있는 스칼라
- **품질 검사 8종 + 봉투** — 커버리지·사전 버전·`service_mix`·`other_share`·경고
- **모집단**: 노트북은 하루 약 100만 행 샘플, 현재는 15일 전수(전이 32.8억 건)

## 재현

노트북 산출 CSV 는 `~/Desktop/리서치/markov/` 에 있다(`*.csv`,
`community_louvain_csv/`, `home_duration_csv/`). 컬럼 이름은 `head -2` 로 확인했고,
현재 쪽은 `analytics/metrics/markov.py::determinism` 과 `analytics/analyses/flow.py`,
`communities.py` 를 읽어 대조했다.
