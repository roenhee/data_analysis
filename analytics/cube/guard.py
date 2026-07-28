"""큐브 SQL의 안전 규약 검증.

- 파티션 프루닝(`date_id`, `c_service_code`)이 없는 쿼리는 5,249억 행 테이블을
  풀스캔하므로 실행 전에 막는다.
- `NOT IN` 은 서브쿼리에 NULL이 하나라도 있으면 조용히 0행을 반환한다. 에러도 나지
  않고 그냥 틀린 답이 나오므로 금지하고 `NOT EXISTS` / `LEFT JOIN` 을 쓴다.
"""
from __future__ import annotations

import re

REQUIRED_PRUNING_COLUMNS = ("date_id", "c_service_code")

_NOT_IN = re.compile(r"\bnot\s+in\b", re.IGNORECASE)


class GuardError(ValueError):
    """SQL 안전 규약 위반."""


def assert_safe_sql(sql: str) -> None:
    for column in REQUIRED_PRUNING_COLUMNS:
        if column not in sql:
            raise GuardError(
                f"partition pruning column {column!r} is absent; "
                "the query would full-scan all_tiara_n"
            )
    if _NOT_IN.search(sql):
        raise GuardError(
            "NOT IN is banned (NULL in the right-hand side silently yields "
            "zero rows); use NOT EXISTS or a LEFT JOIN instead"
        )
