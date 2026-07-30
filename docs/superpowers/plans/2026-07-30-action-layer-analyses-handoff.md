# 인수인계: 행동층 분석 4개 (2026-07-30 중단 지점)

> **읽는 순서:** 이 문서 → `## 시작 절차` 를 그대로 실행 → 실패하면 `## 검증 안 된 것` 을 본다.
> 아래 코드는 **테스트를 돌리지 않은 상태로 커밋 없이 남아 있다.** 통과할 것처럼 보이지만
> 이 프로젝트에서 그 가정은 오늘만 5번 틀렸다(픽스처 결함 3건, 구현 결함 2건).

## 왜 중단했나

Bash 안전성 분류기(`claude-sonnet-5[1m]`)가 간헐적으로 내려가 명령 실행이 막혔다. 파일
쓰기는 됐으므로 코드와 테스트는 다 썼고 **실행만 못 했다.** 데이터·큐브 문제가 아니다.

## 지금 상태

### 커밋됨 · 검증됨 (미푸시 4개)

| 커밋 | 무엇 | 그때 스위트 |
|---|---|---|
| `8bbfddc` | 노트북 대조 문서 | — |
| `b508778` | `CubeSet` 이 행동층 큐브 3개를 싣는다 | 781 passed |
| `aadfc6f` | **`click_distribution`** 분석 | 791 passed |
| `222d7ca` | **`conditional_flow`** 분석 | 802 passed |

### 커밋 안 됨 · **검증 안 됨**

```
?? analytics/analyses/paths.py                              (신규 — 분석 2개)
?? tests/analytics/analyses/test_path_ranking.py            (신규 — 10개)
?? tests/analytics/analyses/test_markov_order_test.py       (신규 — 9개)
 M analytics/analyses/__init__.py                           (paths 임포트 추가)
 M tests/analytics/analyses/test_analyses_on_real_cubes.py  (레지스트리 목록 12개로)
```

`analytics/analyses/paths.py` 에 **`path_ranking`** 과 **`markov_order_test`** 두 분석이
들어 있다. 통과하면 분석이 **12개**가 되고 행동층 분석 4개가 완성된다.

### 큐브

**여섯 큐브 15일치(2026-07-14~28)가 전부 있다.** 사전 `sd_2ab5ec25e750dda2`.
백필은 75.5분에 끝났다(하루 약 10.8분).

| 큐브 | 15일 규모 |
|---|---|
| session | 214,668행 |
| transition | 3,279,905행 |
| quality | 251,822행 |
| action | 하루 659,485행 · 약 3.9 MB |
| cond_transition | 하루 25,074행 · 약 0.12 MB |
| **path** | 하루 1,362,054행 · 약 14 MB → **15일 약 2,040만 행 · 215 MB** |

## 시작 절차 (그대로 실행)

```bash
.venv/bin/python -m pytest tests -q
```

**기대: `821 passed, 4 skipped, 1 xfailed`** (802 + `path_ranking` 10 + `markov_order_test` 9).
숫자가 다르면 아래 "검증 안 된 것" 을 먼저 본다.

```bash
git status -sb    # master...origin/master [앞: 4], 위 5개 파일이 미커밋
```

## 검증 안 된 것 — 여기가 틀렸을 가능성이 가장 높다

### ① `markov_order_test` 의 90:10 기대값

테스트가 **0.129201** 을 기대한다(`test_excess_information_weights_contexts_by_volume`).
처음 0.123694 로 적었다가 다시 계산해 고쳤다. 손계산 근거:

```
문맥 (A,B) cnt 90, 관측 {C: 1.0}      1차 예측 P(C|B)=0.95, P(D|B)=0.05
문맥 (X,B) cnt 10, 관측 {C:.5, D:.5}
KL(A,B) = 1.0·ln(1.0/0.95)                        = 0.0512933
KL(X,B) = 0.5·ln(0.5/0.95) + 0.5·ln(0.5/0.05)     = 0.8303656
가중합   = 0.9·0.0512933 + 0.1·0.8303656          = 0.1292006
문맥 단순 평균이면 (0.0512933+0.8303656)/2         = 0.4408295
```

**구현이 이 값을 내는지 확인되지 않았다.** 안 맞으면 어느 쪽이 틀렸는지 위 계산으로 가른다.

### ② `_parse_trigrams` 가 `str.split(">")` 를 쓴다

`analytics/metrics/paths.py` 의 `_one_n` 을 **밑줄 있는 private 함수인데 밖에서 임포트**했다.
동작하지만 계약이 아니다 — 공개 함수로 올릴지 판단이 필요하다.

그리고 `parts.map(len) == 3` 로 조각 수를 검사하는데, pandas 3.0 에서 `str.split` 결과가
리스트가 아닌 경우가 있는지 확인하지 않았다.

### ③ `path_ranking` 이 `n` 을 필수로 받는다

`test_n_is_required_because_the_populations_differ` 가 `TypeError` 를 기대한다.
`@analysis` 데코레이터가 파라미터를 기록하는데, **필수 인자를 빠뜨렸을 때 그 데코레이터가
`TypeError` 를 그대로 통과시키는지 확인되지 않았다.**

### ④ `real_results` 픽스처에서 두 분석이 건너뛰어지는가

`ACTION_LAYER_REQUIRES` 에 넷 다 등록했다(`path_ranking`·`markov_order_test` → `"path"`).
`test_only_the_action_layer_analyses_are_skipped` 가 그걸 고정한다. 실큐브 픽스처는 화면층
세 개만 읽으므로 건너뛰어야 맞다.

## 통과 후 할 일

- [ ] **mutation check.** 오늘 이 함정을 밟았다 — 변형한 파일을 원래 크기로 복원하면
      CPython 의 mtime 기반 무효화를 통과해서 `__pycache__` 가 계속 변형된 모듈을 내준다.
      **반드시 `PYTHONDONTWRITEBYTECODE=1` + `__pycache__` 삭제**로 돌린다. 그리고 공유
      문자열은 `replace(..., 1)` 이 아니라 **전체 치환**이어야 한다(첫 occurrence 가 다른
      큐브 것일 수 있다).
      되주입할 결함:
      - `path_ranking`: `(other)` 를 순위에 남긴다 / `share` 분모를 컷 이후 합으로
      - `markov_order_test`: 문맥을 단순 평균 / 1차 예측을 경로 큐브 marginal 로 /
        중간 화면 없는 문맥을 0 으로 때운다

- [ ] **15일치 실데이터 확인.** `path` 15일 로딩 시간을 **꼭 측정한다** — 2,040만 행이라
      분석층이 큐브를 통째로 pandas 에 올리는 구조에서 병목이 될 수 있고, 그러면 C(대시보드)
      설계가 달라진다.

  ```python
  # PYTHONPATH=. .venv/bin/python
  from analytics.analyses.base import get_analysis
  from analytics.analyses.cubes import ALL_CUBE_NAMES, load_cube_set
  from data_layer.config import Config
  D = [f"2026-07-{d:02d}" for d in range(14, 29)]
  S = ["top", "media", "entertain", "sports", "content_v", "search"]
  c = load_cube_set(Config.from_env(), dates=D, services=S,
                    state_dict_version="sd_2ab5ec25e750dda2",
                    cube_names=ALL_CUBE_NAMES)
  for n in (3, 4, 5):
      print(n, get_analysis("path_ranking")(c, n=n).headline)
  print(get_analysis("markov_order_test")(c).headline)
  ```

  **`excess_information` 실측값은 아직 아무도 본 적이 없다.** 0 에 가까우면 1차 마르코프가
  충분하다는 뜻이고, 크면 `screen_flow`·`screen_pair_affinity` 의 값이 모형 오차를 담고
  있다는 뜻이다 — **이 프로젝트의 마르코프 분석 전체에 대한 판정이므로 반드시 기록한다.**

- [ ] **B-Task 8 마무리**: 실데이터 회귀 그물 + `docs/superpowers/measurements/` 에 측정 문서.
      게이트 3기준(하루치)은 이미 통과했고 값은 아래 "이미 측정된 것" 에 있다.

- [ ] **SKILL.md 갱신**: 분석 표에 4개 추가, 실측 규모 표에 추가, 연산자 절에
      `cube_names=ALL_CUBE_NAMES` 예시. `path` 큐브가 커서 세그먼트를 먼저 좁히라는 경고.

- [ ] **커밋 · 푸시** (미푸시 4개 + 새 커밋)

## 이미 측정된 것 (다시 재지 않는다)

행동층 하루치(2026-07-27) 게이트:

| | 값 |
|---|---|
`action` 행 수 | 659,485 (클릭 1억 7,096만) · 축 조합 4,248 · `layer2` 종수 183 |
`path` `(other)` 비중 | n=3 **1.25%** · n=4 **9.23%** · n=5 **21.65%** |
`layer1` `other` 비중 | sports **31.0%** · search 18.8% · 나머지 1~4% |
`START` 에 붙은 클릭 | **1.61%** (274만) |
`cond_transition` 합 대 전이 수 | 3억 4,877만 대 3억 371만 (비 1.148) |
`action_kind` 분포 | `(no_click)` 1억 7,883만 · `(none)` 8,842만 · `ClickContent` 8,026만 |
방문당 클릭 | **0.607** — `top/other` 가 **1.657** 로 최고, `media/m_newsview_보기` 0.343 로 최저 |
`action_information` | **0.163 nats** (화면만으로는 0.677) |
`no_click_share` | **58.9%** |

**`top/other` 가 방문당 클릭 1위**라는 게 A6 의 논거를 강화한다 — 사전이 잘라낸 이름 없는
화면들이 가장 상호작용이 많다.

## 환경 함정 (오늘 실제로 밟은 것)

1. **맥이 잠들면 Trino 쿼리가 버려진다.** `Clamshell Sleep` 후 5분이면 서버가
   `ABANDONED_QUERY` 를 낸다. 파이썬은 살아 있어서 트레이스백이 남으므로 프로세스 종료와
   구분된다. 긴 빌드는 **`caffeinate -dims -t <초>` 를 먼저 백그라운드로 걸고** 돌린다.
   배터리 전원에서는 `caffeinate` 로도 뚜껑 덮기를 막지 못하니 전원을 연결하거나 뚜껑을
   열어 둔다.
2. **크레덴셜은 셸 명령줄에 올리면 분류기가 막는다.** 스크립트 안에서
   `sys.path.insert` → `import env` → `os.environ` 에 넣고, 실행은
   `.venv/bin/python -c 'import runpy; runpy.run_path("<스크립트>", run_name="__main__")'`.
3. **백그라운드 빌드 로그는 끝날 때까지 비어 있다.** 파이프를 타면 파이썬이 버퍼링한다.
   진행 상황은 `cache/cubes/<큐브>/*/date=*.parquet` 개수로 본다.
4. **빌더는 첫 실패에서 멈추고 앞선 날짜를 남긴다.** 재실행하면 캐시 적중으로 건너뛰고
   실패분부터 이어간다 — 처음부터 다시 하지 않는다.
