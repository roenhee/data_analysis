from __future__ import annotations

import hashlib
import json
from datetime import date, timedelta


def content_hash(*parts) -> str:
    """입력의 안정적 16자 sha256. dict 키 순서에 무관."""
    blob = json.dumps(parts, sort_keys=True, default=str, ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


def day_strings(start: str, end: str) -> list[str]:
    """[start, end] 양끝 포함 ISO 날짜 문자열 리스트."""
    s = date.fromisoformat(start)
    e = date.fromisoformat(end)
    if e < s:
        raise ValueError(f"end {end} is before start {start}")
    out: list[str] = []
    d = s
    while d <= e:
        out.append(d.isoformat())
        d += timedelta(days=1)
    return out
