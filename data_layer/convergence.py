from __future__ import annotations


def check_convergence(analysis_fn, sizes: list, tol: float = 0.05) -> dict:
    """표본 크기를 키우며 핵심 지표가 안정되는지 확인.

    analysis_fn(size) -> dict[str, float]. 연속한 크기 사이의 상대 변화 최대값이
    tol 이하이면 stable=True.
    """
    results = [{"size": s, "metrics": analysis_fn(s)} for s in sizes]

    max_change = 0.0
    for prev, cur in zip(results, results[1:]):
        for key, cur_val in cur["metrics"].items():
            prev_val = prev["metrics"].get(key)
            if prev_val in (None, 0):
                continue
            change = abs(cur_val - prev_val) / abs(prev_val)
            max_change = max(max_change, change)

    return {"results": results, "max_change": max_change, "stable": max_change <= tol}
