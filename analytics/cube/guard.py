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
_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)


class GuardError(ValueError):
    """SQL 안전 규약 위반."""


def _filter_text(sql: str) -> str:
    """주석을 지우고 첫 `WHERE` 이후 텍스트만 남긴다.

    프루닝 컬럼이 SELECT 목록이나 주석에만 등장하는 것을 '프루닝됨'으로 오인하지 않기
    위한 것이다. `WHERE` 가 아예 없으면 빈 문자열을 반환해 반드시 거부되게 한다.
    """
    stripped = _BLOCK_COMMENT.sub(" ", sql)
    stripped = _LINE_COMMENT.sub(" ", stripped)
    m = _WHERE.search(stripped)
    return stripped[m.end():] if m else ""


def assert_safe_sql(sql: str) -> None:
    """큐브 SQL의 안전 규약을 검사하고 위반 시 `GuardError` 를 던진다.

    이 함수는 "프루닝이 유효하다"가 아니라 "프루닝 컬럼이 필터 위치에 있다"를 보증한다.

    **알려진 한계 (모두 파서가 필요해 의도적으로 남긴다)**

    1. 서브쿼리 안에서만 제약되어 바깥 스캔이 안 잘리는 경우를 잡지 못한다.
    2. `WHERE`/`--` 탐지가 문자열 리터럴을 구분하지 못한다. 리터럴 안의 `--` 는
       뒤쪽 실제 필터를 잘라내 정상 쿼리를 오거부할 수 있고(안전한 방향), 리터럴 안의
       `WHERE` 는 실제 `WHERE` 가 없는 쿼리를 통과시킬 수 있다(위험한 방향).

    호출자는 우리 자신의 SQL 빌더(Task 12)이고, 그 빌더는 블록 주석을 쓰지 않으며
    리터럴은 `_lit()` 로 이스케이프된 열거값(날짜·서비스코드·버전)뿐이라 위 형태를
    만들지 않는다. 외부 입력을 받게 되면 토크나이저가 필요하다.
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
