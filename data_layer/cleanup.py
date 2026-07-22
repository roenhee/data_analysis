from __future__ import annotations


def filter_prefixed(names: list[str], prefix: str) -> list[str]:
    return [n for n in names if n.startswith(prefix)]


def drop_temp_tables(conn, catalog: str, schema: str, prefix: str) -> list[str]:
    """`prefix`로 시작하는 서버 임시 테이블을 모두 DROP. 정리된 이름 리스트 반환."""
    cur = conn.cursor()
    cur.execute(f"SHOW TABLES FROM {catalog}.{schema}")
    names = [r[0] for r in cur.fetchall()]
    targets = filter_prefixed(names, prefix)
    for name in targets:
        cur.execute(f"DROP TABLE IF EXISTS {catalog}.{schema}.{name}")
    return targets
