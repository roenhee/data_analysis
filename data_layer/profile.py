from __future__ import annotations

import pandas as pd

from data_layer.sql_builder import build_action_counts_sql


def compute_dictionary(
    counts: pd.DataFrame,
    cutoff: float = 0.95,
    mapping_rules: dict | None = None,
) -> dict:
    """action_name 카운트로부터 사전 생성.

    counts: columns [action_name, cnt].
    cutoff: 누적 비율. 이 비율을 넘기는 첫 항목까지 vocabulary에 포함.
    mapping_rules: action_name -> state 오버라이드. 없으면 vocab은 자기 자신, 그 외 'other'.
    """
    mapping_rules = mapping_rules or {}
    df = counts.sort_values("cnt", ascending=False).reset_index(drop=True)
    total = df["cnt"].sum()
    df["cum_ratio"] = df["cnt"].cumsum() / total

    vocabulary: list[str] = []
    for _, row in df.iterrows():
        vocabulary.append(row["action_name"])
        # strict `>`: an item landing exactly on the cutoff is not enough to
        # stop — include up to the first item that *crosses* it. Do not change
        # to `>=` (it truncates the vocabulary one item early).
        if row["cum_ratio"] > cutoff:
            break

    vocab_set = set(vocabulary)
    mapping: dict[str, str] = {}
    for name in df["action_name"]:
        if name in mapping_rules:
            mapping[name] = mapping_rules[name]
        elif name in vocab_set:
            mapping[name] = name
        else:
            mapping[name] = "other"

    return {"cutoff": cutoff, "vocabulary": vocabulary, "mapping": mapping}


def build_dictionary(
    source,
    window: tuple[str, str],
    cutoff: float = 0.95,
    mapping_rules: dict | None = None,
    counts_fetcher=None,
) -> dict:
    """Phase 0: 서버에서 action_name 카운트를 훑어 사전 생성.

    counts_fetcher(source, window) -> DataFrame[action_name, cnt].
    테스트에서는 가짜 fetcher를 주입한다. 실제 구현은 fetch_action_counts를 쓴다.
    """
    if counts_fetcher is None:
        counts_fetcher = fetch_action_counts
    counts = counts_fetcher(source, window)
    return compute_dictionary(counts, cutoff=cutoff, mapping_rules=mapping_rules)


def fetch_action_counts(source, window: tuple[str, str]) -> pd.DataFrame:
    """실 Trino에서 기간 내 action_name 카운트만 집계 (Phase 0, 가벼움)."""
    from data_layer.connection import connect

    sql = build_action_counts_sql(source, window)
    conn = connect(source)
    try:
        cur = conn.cursor()
        cur.execute(sql)
        rows = cur.fetchall()
        cols = [d[0] for d in cur.description]
        return pd.DataFrame(rows, columns=cols)
    finally:
        conn.close()
