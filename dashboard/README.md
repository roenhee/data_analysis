# 대시보드 (단일 모드)

    PYTHONPATH=. .venv/bin/streamlit run dashboard/app.py

숫자는 전부 `analytics/analyses/` 에서 온다 — 대시보드는 세그먼트·파라미터를 받아
분석을 부르고 그린다. 상태는 URL 에 있어 주소를 공유하면 같은 화면이 재현된다.

설계: `docs/superpowers/specs/2026-08-04-dashboard-design.md`
비교 모드는 둘째 계획서, graph 렌더는 셋째 계획서다.
