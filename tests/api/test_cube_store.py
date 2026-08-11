"""cube_store: 기간 계산·상한·바이트 예산 캐시·실제 로드."""
import pandas as pd
import pytest

from analytics.analyses.base import CubeSet
from api import cube_store
from api.byte_cache import ByteBudgetCache

# 정본 빌드(7서비스 22일). 구 6서비스 큐브는 디스크에서 삭제됐으므로 여기서도 정본을 쓴다.
_STATE_DICT_VERSION = "sd_68461a6e4fc6ccac"
_SERVICES = ("top", "media", "entertain", "sports", "content_v", "search", "agorax")


def _fake_cubeset(session_rows: int, path_rows: int | None) -> CubeSet:
    session = pd.DataFrame({"period": ["2026-07-14"] * session_rows,
                            "sessions": list(range(session_rows))})
    path = (pd.DataFrame({"path": ["a>b"] * path_rows, "cnt": list(range(path_rows))})
            if path_rows is not None else None)
    return CubeSet(session=session, transition=None, quality=None,
                   state_dict_version="v", services=["top"],
                   requested_dates=[], present_dates=[], path=path)


def test_cubeset_bytes_sums_present_frames():
    cs = _fake_cubeset(session_rows=10, path_rows=5)
    expected = (int(cs.session.memory_usage(deep=True).sum())
                + int(cs.path.memory_usage(deep=True).sum()))
    assert cube_store._cubeset_bytes(cs) == expected


def test_cubeset_bytes_ignores_absent_frames():
    cs = _fake_cubeset(session_rows=10, path_rows=None)
    assert cube_store._cubeset_bytes(cs) == int(cs.session.memory_usage(deep=True).sum())


def test_load_evicts_by_bytes_not_entry_count(monkeypatch):
    # 예산을 세션 큐브 하루치보다도 작게 두면, 서로 다른 기간을 연달아 부를 때
    # 개수와 무관하게 총 바이트가 예산 부근으로 유지된다(마지막 하나만 남는다).
    tiny = ByteBudgetCache(budget_bytes=1, sizeof=cube_store._cubeset_bytes)
    monkeypatch.setattr(cube_store, "_CACHE", tiny)
    cube_store.load(("session",), "2026-07-14", "2026-07-14", _SERVICES, _STATE_DICT_VERSION)
    cube_store.load(("session",), "2026-07-15", "2026-07-15", _SERVICES, _STATE_DICT_VERSION)
    # 두 번째 로드가 첫 번째를 쫓아냈다 — 개수 캐시(옛 maxsize=8)라면 둘 다 남았을 것.
    assert len(tiny._store) == 1
    # 회계는 현재 남은 한 벌뿐 — 누적이 아니다(날짜별 크기는 미세하게 다르다).
    ((_, remaining_size),) = tiny._store.values()
    assert tiny.nbytes == remaining_size


def test_period_days_counts_inclusive():
    assert cube_store.period_days("2026-07-14", "2026-07-14") == 1
    assert cube_store.period_days("2026-07-14", "2026-07-28") == 15


def test_load_rejects_over_hard_limit():
    with pytest.raises(cube_store.PeriodTooLongError):
        cube_store.load(("session",), "2026-01-01", "2026-12-31",
                        ("top",), _STATE_DICT_VERSION)


def test_load_rejects_reversed_range():
    with pytest.raises(ValueError):
        cube_store.load(("session",), "2026-07-16", "2026-07-14",
                        _SERVICES, _STATE_DICT_VERSION)


def test_load_reads_local_session_cube():
    cubes = cube_store.load(("session",), "2026-07-14", "2026-07-16",
                            _SERVICES, _STATE_DICT_VERSION)
    assert cubes.session is not None
    assert set(cubes.present_dates) <= {"2026-07-14", "2026-07-15", "2026-07-16"}
    assert cubes.state_dict_version == _STATE_DICT_VERSION


def test_load_is_cached_same_object():
    args = (("session",), "2026-07-14", "2026-07-16", _SERVICES, _STATE_DICT_VERSION)
    assert cube_store.load(*args) is cube_store.load(*args)
