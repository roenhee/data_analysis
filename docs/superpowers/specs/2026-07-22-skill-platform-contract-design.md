# 스킬 ↔ 플랫폼 경계 계약 설계 (Skill ↔ Platform Contract)

- 날짜: 2026-07-22
- 상태: 설계 확정 (구현 계획 대기)
- 범위: 서브프로젝트 **②(분석 스킬)와 ③(플랫폼)의 공유 경계 계약**. ② 분석 로직 자체와 ③ 플랫폼 UI는 각각 별도 사이클이며, 둘 다 본 계약 위에 올라간다.

## 배경

②(분석 스킬)와 ③(플랫폼)은 접점을 공유한다 — 스킬이 낸 결과를 플랫폼이 읽어 시각화한다. 이 경계를 각자 나중에 맞추면 형식 불일치로 rework가 발생한다. 그래서 **경계 계약을 먼저 공동 설계**해 얼려두고, ②는 "③이 소비할 정확한 형식"을 생산하고 ③은 "②가 내는 그대로" 소비하게 한다. 본 문서는 그 계약만 다룬다. 이 계약은 문서일 뿐 아니라 **공유 코드(`data_layer/results.py`)와 저장 레이아웃·스키마**로 구체화되며, 그 코드는 지금 오프라인으로 구현·테스트할 수 있다.

## 관통 원칙

스킬(②)은 **정확한 데이터 + 방향성 제안**만 낸다. 플랫폼(③)은 **전문 시각화 라이브러리로 렌더하고 대시보드를 조립**한다. 분석은 스킬, 시각화·조립은 플랫폼. 연결은 자동 파이프라인이 아니라 **사람 매개**다: 사용자가 CC에서 스킬을 돌려 결과 파일을 만들고, 플랫폼이 그 파일과 매니페스트를 읽는다.

## 데이터 흐름

```
②스킬 실행 ──publish_result()──▶ cache/results/<id>.parquet   (순수 데이터 테이블)
                                  cache/results/<id>.json      (봉투: viz/insight/...)
                                  cache/manifest.json results[] (색인)
                                            │
③플랫폼 ──list_results()/read_result()─────┘──▶ 시각화 라이브러리로 렌더·조립
```

## 결과 계약 (result contract)

- **단위**: 분석 산출물 1개 = `result` 1개. 한 번의 스킬 실행이 만든 여러 결과는 `run_id`로 묶는다. 플랫폼은 결과를 카드처럼 자유롭게 배치·조합하고, `run_id`로 같은 실행을 함께 볼 수 있다.
- **데이터와 봉투 분리**: 데이터는 순수 테이블(parquet), 봉투(JSON)가 "그걸 어떻게 볼지"를 설명한다.

### 봉투(envelope) 스키마

```
result:
  id             # 고유 id
  run_id         # 같은 스킬 실행 묶음
  skill          # "markov"
  analysis_type  # "transition_matrix" | "stationary_dist" | "exit_prob" ...
  title          # "전이 확률 히트맵"
  created_at
  params         # {window, seed, sample_target, k, thresholds ...}
  config_version # 사전(dictionary)+세션화 버전
  data_ref       # 결과 테이블 parquet 경로
  columns        # [{name, type} ...]  플랫폼이 무엇을 받는지 알게
  viz:                          # "방향성 제안" (어떻게 볼지)
    chart_type   # "heatmap"|"bar"|"line"|"distribution"|"network"|"table"
    encoding     # {x:"from_state", y:"to_state", value:"p", series:...}
  insight        # (선택) 짧은 해석 텍스트. "홈탭→뉴스뷰 전이가 유독 강함"
  caveats        # (선택) 품질 경고. "out_cnt<1000 상태는 신뢰 낮음"
```

- `viz`가 사용자가 말한 **"방향성 제안"**: 스킬은 "히트맵으로, x=from y=to value=p"까지만 제안하고, 실제 렌더는 플랫폼의 전문 라이브러리가 한다.
- `caveats`는 리서치에서 나온 품질 경고(저표본·신뢰구간 등)를 실어 나르는 자리 — ②b(통계 엄밀성)가 채울 여지.
- 봉투 스키마는 지금 이대로 시작하고, 실제 구현에서 필요가 드러나면 필드를 확장한다(특히 `caveats`).

## 저장 레이아웃

```
cache/results/
  <id>.parquet     # 순수 데이터 테이블
  <id>.json        # 봉투(메타)
cache/manifest.json → results[]: 색인
   { id, run_id, skill, analysis_type, title, created_at, config_version,
     data_ref, envelope_ref }
```

플랫폼 소비 흐름: 매니페스트 `results[]`를 읽어 목록화하고 `run_id`로 그룹핑 → 고른 결과의 `.json`(어떻게 볼지)과 `.parquet`(데이터)을 로드 → 시각화 라이브러리로 렌더.

## 계약 API — `data_layer/results.py`

②(생산)와 ③(소비)이 둘 다 의존하는 계약이라, 이미 매니페스트·캐시 경로를 소유한 `data_layer`에 둔다. `query.run`은 범용 로컬 캐시 프리미티브로 유지하고, `publish_result`는 그 위에서 "플랫폼용 결과"를 만드는 얇은 층이다.

- `publish_result(config, run_id, skill, analysis_type, title, data, viz, params, config_version, insight=None, caveats=None) -> id`
  — ②가 호출(생산). `data`(DataFrame)를 `<id>.parquet`로, 봉투를 `<id>.json`으로 쓰고 매니페스트 `results[]`에 색인. `id`는 결정적(run_id + analysis_type 등의 해시) 권장.
- `list_results(config, run_id=None) -> list[envelope-index]`
  — ③이 호출(소비). 매니페스트에서 결과 목록(선택적으로 run_id 필터).
- `read_result(config, id) -> (DataFrame, envelope-dict)`
  — ③이 호출(소비). parquet 데이터 + 봉투 JSON을 함께 반환.

이 API가 계약의 유일한 진입점이다 — ③은 ②의 내부를 몰라도 되고, ②는 ③의 렌더링을 몰라도 된다.

## config_version 정의 (#3 흡수)

- `config_version = content_hash(dictionary_version, sessionization_version)`.
  - `dictionary_version` = Phase 0 사전 아티팩트의 버전(내용 해시).
  - `sessionization_version` = 세션화 파라미터(비활동 타임아웃 등) config의 버전.
- ②는 분석 시 이 값을 `publish_result`에 실어 보내, 결과가 어느 사전/세션화로 만들어졌는지 추적한다.
- 매니페스트 top-level `config` 섹션(`dictionary_version`, `sessionization_version`, `sources_version`)을 이 시점에 채운다.
- 효과: 사전·세션화가 바뀌면 `config_version`이 달라져 결과 캐시가 정확히 구분된다(옛 결과를 새 config에 잘못 재사용하지 않음).

## 스킬 카탈로그 계약 (경량, 두 번째 접점)

플랫폼이 "어떤 스킬이 있고 어떻게 부르나"를 보여주려면 스킬이 자기 소개를 등록해야 한다.

- 각 스킬이 경량 디스크립터를 정해진 위치에 둔다:
  ```
  skill_descriptor:
    name          # "markov"
    description   # 한 줄 설명
    invocation    # 어떻게 부르나 (프롬프트/사용법)
    expected_params  # {window, seed, sample_target, ...}
  ```
- 위치: `cache/config/skills_registry.json`(또는 각 스킬 폴더의 디스크립터를 모아 등록). 플랫폼이 읽어 카탈로그로 표시.
- 결과 계약보다 단순하므로 최소만 못박고, 세부(정확한 위치·필드)는 ③ 구현 시 확정 가능. 지금 포함하는 이유는 ② 스킬을 만들 때 디스크립터도 함께 내게 해 rework를 줄이기 위함이다.

## 이 계약이 ①(data_layer)에 주는 변경

- 신규 모듈 `data_layer/results.py` (`publish_result`/`list_results`/`read_result`).
- `Manifest`의 `results[]` 항목 확장(run_id·skill·analysis_type·title·data_ref·envelope_ref 추가). 기존 `add_result`는 유지하되 확장하거나, `publish_result`가 자체적으로 색인.
- 매니페스트 top-level `config` 섹션 채우기 로직.
- 스킬 레지스트리 읽기/쓰기 헬퍼(경량).
- `query.run`은 변경 불필요(범용 프리미티브 유지). `publish_result`가 그 위 얇은 층.

## 성공 기준

- ②가 `publish_result(...)` 한 번으로 계약 준수 결과(데이터+봉투+색인)를 낼 수 있다.
- ③이 `list_results`/`read_result`만으로 결과를 나열·그룹핑·로드할 수 있고, ②의 내부를 알 필요가 없다.
- 데이터(parquet)와 봉투(json)가 분리되어, 플랫폼이 같은 데이터로 다양한 시각화를 시도할 수 있다.
- `config_version`으로 사전/세션화 버전이 다른 결과가 캐시에서 정확히 구분된다.
- 플랫폼이 스킬 레지스트리만 읽어 사용 가능한 스킬 목록·호출법을 표시할 수 있다.
- 봉투 스키마 확장(예: `caveats` 채우기)이 기존 소비자를 깨지 않고 가능하다(추가 필드는 선택적).

## 범위 밖 (별도 사이클)

- ② 분석 스킬의 실제 로직(markov 마이그레이션, 통계 엄밀성, 고급 모델) — 본 계약을 **생산**하는 쪽. 별도 스펙/계획.
- ③ 플랫폼의 UI·시각화 라이브러리 선택·대시보드 편집 — 본 계약을 **소비**하는 쪽. 별도 스펙/계획.
- ①의 다른 deferred 항목(`query.target=server`, `enrich.get_dim`) — 본 계약과 무관, 필요 시 각각 추가.
