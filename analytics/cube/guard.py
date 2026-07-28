"""큐브 SQL의 안전 규약 검증.

- 파티션 프루닝(`date_id`, `c_service_code`)이 없는 쿼리는 5,249억 행 테이블을
  풀스캔하므로 실행 전에 막는다.
- `NOT IN` 은 서브쿼리에 NULL이 하나라도 있으면 조용히 0행을 반환한다. 에러도 나지
  않고 그냥 틀린 답이 나오므로 금지하고 `NOT EXISTS` / `LEFT JOIN` 을 쓴다.
"""
from __future__ import annotations

import re

REQUIRED_PRUNING_COLUMNS = ("date_id", "c_service_code")

# NOT IN 과 <> ALL 은 Trino에서 같은 의미이고 같은 NULL 오염을 갖는다.
_NULL_POISONED = (
    re.compile(r"\bnot\s+in\b", re.IGNORECASE),
    re.compile(r"<>\s*all\b", re.IGNORECASE),
)
_WHERE = re.compile(r"\bwhere\b", re.IGNORECASE)
_LINE_COMMENT = re.compile(r"--[^\n]*")


class GuardError(ValueError):
    """SQL 안전 규약 위반."""


def _filter_text(sql: str) -> str:
    """주석을 지우고 첫 `WHERE` 이후 텍스트만 남긴다.

    프루닝 컬럼이 SELECT 목록이나 주석에만 등장하는 것을 '프루닝됨'으로 오인하지 않기
    위한 것이다. `WHERE` 가 아예 없으면 빈 문자열을 반환해 반드시 거부되게 한다.
    """
    stripped = _LINE_COMMENT.sub(" ", sql)
    m = _WHERE.search(stripped)
    return stripped[m.end():] if m else ""


def assert_safe_sql(sql: str) -> None:
    """큐브 SQL의 안전 규약을 검사하고 위반 시 `GuardError` 를 던진다.

    **한계**: 프루닝 컬럼이 `WHERE` 이후에 독립 토큰으로 등장하는지까지만 본다.
    서브쿼리 안에서만 제약되어 바깥 스캔은 안 잘리는 경우는 잡지 못한다. 그걸 잡으려면
    SQL 파서가 필요하고, 이 가드의 호출자는 우리 자신의 SQL 빌더(Task 12)이므로
    파서까지는 가지 않는다. 이 함수는 "프루닝이 유효하다"가 아니라
    "프루닝 컬럼이 필터 위치에 있다"를 보증한다.
    """
    filters = _filter_text(sql).lower()
    for column in REQUIRED_PRUNING_COLUMNS:
        # 단어 경계: my_date_id_backup 같은 다른 식별자의 부분문자열을 인정하지 않는다.
        if not re.search(rf"\b{re.escape(column)}\b", filters):
            raise GuardError(
                f"partition pruning column {column!r} is absent from the WHERE "
                "clause; add it as a filter or the query will full-scan "
                "all_tiara_n (524 billion rows)"
            )
    for pattern in _NULL_POISONED:
        if pattern.search(sql):
            raise GuardError(
                "NOT IN / <> ALL are banned (a single NULL on the right-hand "
                "side silently yields zero rows); use NOT EXISTS or a LEFT JOIN"
            )
