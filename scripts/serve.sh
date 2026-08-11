#!/usr/bin/env bash
# 사내망 공유용 대시보드 기동 스크립트 (개인 Mac).
#   백엔드(FastAPI/uvicorn) : 0.0.0.0:8000  — 로컬 큐브만 읽음(Trino 크레덴셜 불필요)
#   프론트(Next.js)         : 0.0.0.0:3000  — 브라우저가 백엔드 LAN 주소로 직접 호출
#
# 사용법:
#   scripts/serve.sh start   # 빌드 후 두 서버 기동(백그라운드, 슬립 방지)
#   scripts/serve.sh dev     # 빌드 없이 dev 서버로 기동(개발용)
#   scripts/serve.sh stop    # 두 서버 정지
#   scripts/serve.sh status  # 상태·공유 URL 출력
set -euo pipefail
cd "$(dirname "$0")/.."
ROOT="$(pwd)"
LOG_DIR="$ROOT/.serve-logs"; mkdir -p "$LOG_DIR"

# LAN IP 자동 탐지(유선 en0 우선, 없으면 en1). 다른 인터페이스면 여기 바꾼다.
lan_ip() { ipconfig getifaddr en0 2>/dev/null || ipconfig getifaddr en1 2>/dev/null || echo "127.0.0.1"; }
IP="$(lan_ip)"
API_BASE="http://$IP:8000"

start_backend() {
  echo "▶ 백엔드  $API_BASE  (로컬 큐브, Trino 불필요)"
  # caffeinate: 맥이 잠들면 서버가 죽는다. nohup+disown: 세션 닫아도 지속.
  PYTHONPATH="$ROOT" nohup caffeinate -i "$ROOT/.venv/bin/uvicorn" \
    api.main:app --host 0.0.0.0 --port 8000 \
    > "$LOG_DIR/backend.log" 2>&1 &
  echo $! > "$LOG_DIR/backend.pid"; disown || true
}

start_frontend() {
  local mode="$1"
  if [ "$mode" = "prod" ]; then
    echo "▶ 프론트 빌드 (NEXT_PUBLIC_API_BASE=$API_BASE 를 번들에 인라인)"
    NEXT_PUBLIC_API_BASE="$API_BASE" npm --prefix frontend run build
    echo "▶ 프론트  http://$IP:3000  (프로덕션)"
    nohup caffeinate -i npm --prefix frontend run start -- -H 0.0.0.0 -p 3000 \
      > "$LOG_DIR/frontend.log" 2>&1 &
  else
    echo "▶ 프론트  http://$IP:3000  (dev)"
    NEXT_PUBLIC_API_BASE="$API_BASE" nohup caffeinate -i \
      npm --prefix frontend run dev -- -H 0.0.0.0 -p 3000 \
      > "$LOG_DIR/frontend.log" 2>&1 &
  fi
  echo $! > "$LOG_DIR/frontend.pid"; disown || true
}

stop_all() {
  for name in backend frontend; do
    pid_file="$LOG_DIR/$name.pid"
    [ -f "$pid_file" ] && kill "$(cat "$pid_file")" 2>/dev/null && echo "■ $name 정지" || true
    rm -f "$pid_file"
  done
  # 자식(uvicorn/next)까지 정리.
  pkill -f "uvicorn api.main:app" 2>/dev/null || true
  pkill -f "next (dev|start)" 2>/dev/null || true
}

case "${1:-status}" in
  start) stop_all; start_backend; start_frontend prod
         echo "✅ 공유 URL:  http://$IP:3000" ;;
  dev)   stop_all; start_backend; start_frontend dev
         echo "✅ 공유 URL(dev):  http://$IP:3000" ;;
  stop)  stop_all ;;
  status)
    curl -s -m 3 "http://127.0.0.1:8000/api/meta" >/dev/null 2>&1 && echo "backend  UP ($API_BASE)" || echo "backend  DOWN"
    curl -s -m 3 "http://127.0.0.1:3000" >/dev/null 2>&1 && echo "frontend UP (http://$IP:3000)" || echo "frontend DOWN"
    echo "공유 URL: http://$IP:3000" ;;
  *) echo "사용법: scripts/serve.sh {start|dev|stop|status}"; exit 1 ;;
esac
