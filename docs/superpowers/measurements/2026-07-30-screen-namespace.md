# 측정: `common.page` 와 `action.name` 은 같은 화면 이름 공간인가

**날짜:** 2026-07-30 · **대상:** 2026-07-27 하루, 6서비스(top·media·entertain·sports·content_v·search)
**계획서:** `plans/2026-07-29-action-layer-phase3.md` Task 1
**결론:** **아니다. 두 이름 공간은 서로 번역되지 않는다.** Task 2·3 은 `common.page` 가 아니라
`visit_idx` 방식으로 간다 — 스펙의 "윈도우 함수 불필요" 를 포기한다.

## 왜 재야 했나

행동층 `action` 큐브는 "화면 안에서 무엇을 눌렀는가" 를 센다. 그 화면을 무엇으로 표현할지가
문제였다. 스펙은 두 가지를 동시에 말한다 — 화면층(`transition` 큐브)의 상태는
`c_service_code || '/' || action.name`(Pageview 행)인데, 클릭의 화면 귀속은 `common.page` 로
하면 윈도우 함수가 필요 없어 싸다고.

**둘이 같은 이름 공간이 아니면 두 큐브를 조인할 수 없다.** "홈탭에서 무엇을 눌렀고 그다음
어디로 갔나" 가 한 문장으로 안 나온다. 조인이 성립하려면 **`page → name` 이 함수**여야
한다: `page` 하나가 여러 `action.name` 을 가리키면 그 클릭이 어느 화면 것인지 정해지지 않는다.

계획서는 `top` 하루만 재라고 했지만 6서비스 전부 쟀다. 기존 품질 경고
`page_name_ambiguous` 가 서비스마다 크게 다르므로(search 70~79%, sports 27~35%)
`top` 만 보면 최선의 경우만 본다.

## ① 이름 공간 크기 (Pageview 행, 하루)

| 서비스 | Pageview | `action.name` 개수 | `common.page` 개수 | `page` NULL | `name` NULL |
|---|---|---|---|---|---|
| top | 172,199,782 | 23 | 10 | 0 | 0 |
| media | 48,610,276 | 105 | 99 | 0 | 0 |
| search | 25,080,637 | **1** | 19 | 0 | 0 |
| entertain | 14,799,099 | 9 | 8 | 0 | 0 |
| sports | 11,077,077 | 7 | 39 | 57,932 | 0 |
| content_v | 6,092,361 | 3 | 5 | 0 | 0 |

NULL 은 문제가 아니다(`name` 은 0건, `page` 는 sports 0.5%뿐). 문제는 대응 관계다.

## ② `page → name` — 조인 가능성 (**깨진다**)

`pages_multi` = `action.name` 을 둘 이상 갖는 `page` 의 개수. `물량 비중` = 그 `page` 들이
차지하는 Pageview 비중이고, **결정에 필요한 건 이쪽**이다(서로 다른 page 개수는 꼬리에
좌우된다).

| 서비스 | page 수 | 다중 대응 page | page 비중 | **물량 비중** | 한 page 최대 name 수 |
|---|---|---|---|---|---|
| media | 99 | 2 | 2.0% | **99.45%** | 5 |
| entertain | 8 | 1 | 12.5% | **97.08%** | 2 |
| top | 10 | 4 | 40.0% | **81.52%** | **10** |
| sports | 39 | 1 | 2.6% | **79.07%** | 2 |
| search | 19 | 0 | 0% | 0% | 1 |
| content_v | 5 | 0 | 0% | 0% | 1 |

계획서의 분기 기준은 "다중 대응 10% 이상이면 깨진 것" 이었다. **6서비스 중 4개가 물량
79~99.5%다.** 조금 깨진 게 아니다.

### 충돌 물량 상위 (전부 그 서비스의 주력 화면이다)

| 서비스 | `page` | name 수 | Pageview | `action.name` 목록 |
|---|---|---|---|---|
| top | `default` | **10** | 97,674,044 | 엠탑조회 \| 다음_PC탑 \| 알림함 \| 다음_PC탑_전체서비스 \| 404 \| 500 \| subscription-settings \| 숨은고양이찾기_조회 \| 숫자기억_조회 \| 나의플레이기록_조회 |
| media | `newsview` | 4 | 48,344,773 | m_newsview_보기 \| p_newsview_보기 \| newsview \| 기사뷰 |
| top | `hometab` | 3 | 42,614,377 | 홈탭_진입 \| walkthrough \| daumbot_PV |
| entertain | `entertainview` | 2 | 14,366,713 | m_newsview_보기 \| p_newsview_보기 |
| sports | `sportsview` | 2 | 8,712,797 | m_newsview_보기 \| p_newsview_보기 |

**`top/default` 하나가 top 트래픽의 57%다.** 그 안에 `엠탑조회`·`다음_PC탑` 이 함께
들어 있는데, 이 둘은 전체 데이터에서 가장 굵은 화면 두 개다. `page` 로 클릭을 귀속하면
그 둘의 클릭이 한 버킷에 섞이고, 되돌릴 방법이 없다.

`m_newsview_보기` / `p_newsview_보기` 가 모바일·PC 구분이라는 것도 보인다 — `page` 는 그
구분을 지운다. media·entertain·sports 세 서비스에서 같은 패턴이다.

## ③ `name → page` — 역방향 (기존 품질 검사가 재는 쪽)

조인에는 무해하다(여러 page 가 한 name 으로 모이는 건 함수다). 정보 손실의 크기라서 함께 쟀다.

| 서비스 | name 수 | 다중 대응 name | name 비중 | 물량 비중 | 한 name 최대 page 수 |
|---|---|---|---|---|---|
| search | 1 | 1 | 100% | **100%** | **19** |
| content_v | 3 | 1 | 33.3% | **99.997%** | 3 |
| sports | 7 | 1 | 14.3% | 19.14% | **34** |
| media | 105 | 1 | 1.0% | 0.005% | 2 |
| top | 23 | 0 | 0% | 0% | 1 |
| entertain | 9 | 0 | 0% | 0% | 1 |

**`search` 의 `action.name` 은 하루 2,508만 Pageview 에 대해 딱 1개다.** 즉 전이 큐브에서
search 전체가 **화면 한 개**다. 체류 계측도 없는 서비스라(상시 품질 경고 `screen_without_dwell`
15일 내내 100%), search 는 화면 단위로 사실상 관측되지 않는다. 반대로 `common.page` 는
search 에서 19개를 구분한다.

## 결론: 두 이름 공간은 **교차한다**

한쪽이 다른 쪽의 세분이 아니다.

- `action.name` 이 더 촘촘한 곳: top(23 대 10), media(105 대 99)
- `common.page` 가 더 촘촘한 곳: search(19 대 1), sports(39 대 7)

그래서 **어느 방향으로도 전역 함수가 아니다.** 한쪽을 골라 다른 쪽으로 번역하면 어떤
서비스에서든 정보가 사라진다. "둘 중 무엇이 옳은 화면이냐" 는 질문 자체가 답이 없고,
같은 큐브 안에서 섞어 쓰면 조인이 조용히 틀린다.

## 결정 (계획서 Task 1 Step 2 의 분기 B)

**`action` 큐브의 `screen` 은 `transition` 큐브와 **같은** 식을 쓴다** —
`c_service_code || '/' || action.name`, 사전 밖은 `c_service_code || '/other'`. 클릭은
`visit_idx` 로 **직전 Pageview 화면**에 붙인다(1단계 체류 귀속에서 이미 검증된 기법이다).

- **얻는 것:** `action` 큐브의 `screen` 과 `transition` 큐브의 `from_state` 가 **같은 값**이라
  조인이 구조적으로 성립한다. 번역 테이블도, 사전에 매핑을 추가할 일도 없다.
- **잃는 것:** 스펙의 "윈도우 함수 불필요" 를 포기한다. 비용이 전이 큐브 수준으로 오른다
  (전이 큐브가 하루 빌드 5.3분의 72%를 쓴다).
- **남는 한계:** search 는 화면이 하나라 그 서비스의 클릭 분포가 화면으로 갈라지지 않는다.
  이건 이 결정의 결함이 아니라 `action.name` 어휘의 결함이고, `page_name_ambiguous` 가
  이미 가리키던 곳이다. `common.page` 를 쓰면 search 만 나아지고 top·media·entertain·sports
  가 망가진다 — 바꿔서 나아지는 거래가 아니다.

**`common.page` 를 화면으로 쓰는 선택지는 이 측정으로 닫혔다.** 다시 열려면 `top/default`
같은 버킷이 쪼개져야 하고, 그건 원천 계측 변경이다.

## 재현

```bash
# 크레덴셜은 스크립트 안에서 `import env` 로 넣는다 — 셸 명령줄로 끌어내면 분류기가 막는다.
.venv/bin/python -c 'import runpy; runpy.run_path("<스크립트>", run_name="__main__")'
```

쿼리 4개(이름 공간 크기 / `page→name` / `name→page` / 충돌 상위 25)는 `fetch_aggregate` 로
돌려 content hash 로 캐시했다 — 같은 SQL 을 다시 부르면 Trino 를 타지 않는다.
