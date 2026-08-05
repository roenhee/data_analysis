# 대시보드 (단일 모드)

    PYTHONPATH=. .venv/bin/streamlit run dashboard/app.py

숫자는 전부 `analytics/analyses/` 에서 온다 — 대시보드는 세그먼트·파라미터를 받아
분석을 부르고 그린다. 상태는 URL 에 있어 주소를 공유하면 같은 화면이 재현된다.

## 레이아웃 (B형 — 상단 컨트롤바)

- **상단 컨트롤바**: `[단일|비교]` 토글(비교는 준비 중, 자리만) + 기간·서비스·세그먼트 축.
- **분석 탭**: 개요·화면흐름·행동·서비스·품질.
- **사이드바**: 분석 선택 + 파라미터만(얇음).
- **메인**: 지표카드 → 차트 → 표 → 경고 봉투.

## 시각화 · 표

- 차트는 **Vega-Lite(Altair)** — `st.altair_chart`. bar/line/heatmap 을 `viz.kind` 로 그린다.
- 차트는 **상위 N개 고정 렌더**(막대 수천 개 방지), 표는 **페이지네이션**으로 전 행을 다 본다.

설계: `docs/superpowers/specs/2026-08-04-dashboard-design.md`,
`docs/superpowers/specs/2026-08-05-dashboard-ux-revamp-design.md`
비교 모드는 둘째 계획서, graph 렌더는 셋째 계획서다.
