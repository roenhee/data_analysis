# 대시보드 서버 런칭 가이드 (사내망 공유)

개인 Mac에서 대시보드를 띄워 **같은 사내망의 다른 사람들이 브라우저로 접속**하게 하는
구체 절차다. 배포 파이프라인 없이 이 맥이 곧 서버다(설계 결정: 개인 PC 사내망 공유).

## 구조 — 두 프로세스

| 프로세스 | 무엇 | 포트 | 크레덴셜 |
|---|---|---|---|
| **백엔드** FastAPI(uvicorn) | 로컬 큐브 parquet 를 읽어 분석 JSON 을 냄 | **8000** | **불필요** (로컬 큐브만 읽음. Trino 는 큐브 *빌드* 때만) |
| **프론트** Next.js | 브라우저가 받는 화면. 백엔드를 HTTP 로 호출 | **3000** | 불필요 |

**핵심 함정 셋** (안 지키면 "내 맥에선 되는데 남들은 안 됨"):
1. **두 서버를 `0.0.0.0` 에 바인딩**해야 사내망에서 보인다(`127.0.0.1`은 이 맥 전용).
2. **브라우저는 남의 기기에서 도니 `localhost:8000` 이 아니라 이 맥의 LAN IP** 로 백엔드를
   불러야 한다 → 프론트에 `NEXT_PUBLIC_API_BASE=http://<이_맥_LAN_IP>:8000` 을 준다.
   이 값은 **빌드 시점에 번들에 박힌다**(NEXT_PUBLIC_*). 그래서 IP 가 바뀌면 다시 빌드한다.
3. **맥이 잠들면 서버가 죽는다** → `caffeinate` 로 감싼다.

## 한 줄 실행 (권장)

```bash
scripts/serve.sh start
```

이게 하는 일: LAN IP 자동 탐지 → 백엔드(0.0.0.0:8000) 기동 → 프론트를 그 IP 로 빌드 →
프론트(0.0.0.0:3000) 기동. 전부 `caffeinate`(슬립 방지) + `nohup`(세션 닫아도 지속). 끝나면
**공유 URL `http://<LAN_IP>:3000`** 을 출력한다. 그 URL 을 동료에게 준다.

- 개발/빠른 확인: `scripts/serve.sh dev` (빌드 없이 dev 서버, 조금 느리지만 즉시).
- 정지: `scripts/serve.sh stop` · 상태: `scripts/serve.sh status`
- 로그: `.serve-logs/backend.log` · `.serve-logs/frontend.log`

## 수동 실행 (스크립트 없이, 원리 이해용)

```bash
# 0) 이 맥의 LAN IP 확인 (예: 172.26.187.124)
ipconfig getifaddr en0

# 1) 백엔드 — 0.0.0.0 바인딩, 슬립 방지, 백그라운드
PYTHONPATH=. nohup caffeinate -i .venv/bin/uvicorn api.main:app \
  --host 0.0.0.0 --port 8000 > .serve-logs/backend.log 2>&1 &

# 2) 프론트 — LAN IP 를 번들에 박아 빌드한 뒤 프로덕션 기동
NEXT_PUBLIC_API_BASE=http://172.26.187.124:8000 npm --prefix frontend run build
nohup caffeinate -i npm --prefix frontend run start -- -H 0.0.0.0 -p 3000 \
  > .serve-logs/frontend.log 2>&1 &

# 3) 동료가 접속할 주소
echo http://172.26.187.124:3000
```

`dev` 로 띄우려면 2)의 build 를 생략하고:
```bash
NEXT_PUBLIC_API_BASE=http://172.26.187.124:8000 \
  npm --prefix frontend run dev -- -H 0.0.0.0 -p 3000
```

## 사전 준비 (최초 1회)

- Python 가상환경 `.venv` (설치돼 있음). 백엔드 의존: fastapi·uvicorn (설치됨).
- Node `node_modules`: `npm --prefix frontend install` (설치됨).
- 검증된 환경: node v24.13 · Python 3.14 · Next 16.3.

## macOS 방화벽

시스템 설정 → 네트워크 → 방화벽이 켜져 있으면 **들어오는 연결을 처음에 차단**한다.
- 방화벽을 끄거나, `uvicorn`·`node`(next) 프로세스의 "들어오는 연결 허용" 을 승인한다.
- 첫 외부 접속 시 허용 팝업이 뜨면 **허용**을 누른다.
- 확인: 다른 기기에서 `http://<LAN_IP>:8000/api/meta` 가 JSON 을 주면 백엔드가 열린 것.

## 재부팅 후 지속

`caffeinate` 는 **슬립**은 막지만 **재부팅**엔 안 남는다. 재부팅 후엔 `scripts/serve.sh start`
를 다시 실행하면 된다. 완전 자동(로그인 시 자동 기동)을 원하면 `launchd` 사용자 에이전트
(`~/Library/LaunchAgents/*.plist`)로 `scripts/serve.sh start` 를 걸 수 있다(선택).

## 메모리 주의 (재조사 불필요)

- 이 맥 RAM 36GB. `path_ranking` 등은 path 큐브(하루 ~245MB) 를 로드한다 — 첫 무거운 조회는
  큐브를 캐시에 올려 ~15초, 이후 즉시. 캐시는 **바이트 예산 16GiB**(`api/cube_store.py`
  `CACHE_BUDGET_BYTES`)로 잘려 OOM 을 막는다. 여러 사람이 봐도 큐브는 한 벌 공유라 메모리 일정.
- 기간 상한: 소프트 31일(경고) · 절대 90일(거부). 1년치를 한 번에 올리면 안 되게 막혀 있다.

## 문제 해결

| 증상 | 원인 / 조치 |
|---|---|
| 동료가 화면은 뜨는데 데이터가 안 나옴 | 프론트가 `localhost:8000` 을 부름 → **LAN IP 로 다시 빌드**(함정 2). `.serve-logs/frontend.log` 와 브라우저 콘솔의 fetch 주소 확인 |
| 아무도 접속 못 함 | 서버가 `127.0.0.1` 바인딩 → `--host 0.0.0.0`·`-H 0.0.0.0` 확인. 또는 방화벽 |
| 잠시 뒤 죽음 | 맥 슬립 → `caffeinate` 로 감쌌는지 확인 |
| 백엔드 500 | `.serve-logs/backend.log` 확인. 큐브 미빌드면 해당 분석만 실패(로컬 큐브 범위 밖 날짜) |
| 큐브를 새로 빌드해야 함 | 그건 서빙과 별개 — Trino 크레덴셜(`env.py`) 필요. `scripts/build_cubes.py` 참고 |
