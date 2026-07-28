"""큐브 빌드 CLI.

사용:
    .venv/bin/python scripts/build_cubes.py 2026-07-27 2026-07-27 top,media

테이블 좌표는 `sources.json` 에서 읽어 빌더에 넘긴다 — 빌더의 기본 상수에 기대지
않으므로 좌표가 바뀌면 쿼리도 같이 바뀐다.
"""
from __future__ import annotations

import sys
from pathlib import Path

# `pythonpath = .` 는 pytest 에만 적용된다. 스크립트로 직접 돌 때도 리포 루트를 찾게 한다.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from analytics.cube.builder import SOURCES_PATH, build_cubes, build_state_dict  # noqa: E402
from data_layer.config import Config  # noqa: E402
from data_layer.sources import load_sources  # noqa: E402


def main(argv: list[str]) -> int:
    if len(argv) != 4:
        print(__doc__)
        return 2
    start, end, services_csv = argv[1], argv[2], argv[3]
    services = [s.strip() for s in services_csv.split(",") if s.strip()]

    config = Config.from_env()
    config.ensure_dirs()
    sources = load_sources(Path(SOURCES_PATH))
    events = sources["events"]
    demography = sources["demography"]

    print(f"[1/2] state 사전 생성 {start}~{end} {services}")
    sd = build_state_dict(
        config, window=(start, end), services=services,
        events_table=events.qualified_name(),
    )
    print(f"      version={sd.version()} screens={len(sd.screens)} "
          f"layer1={len(sd.layer1)} layer2={len(sd.layer2)} "
          f"versions={len(sd.app_versions)}")

    print("[2/2] 큐브 빌드")
    written = build_cubes(
        config, state_dict=sd, window=(start, end), services=services,
        source_version=events.version(),
        events_table=events.qualified_name(),
        demography_table=demography.qualified_name(),
    )
    for p in written:
        size_kb = p.stat().st_size / 1024
        print(f"      {p}  ({size_kb:,.0f} KB)")
    if not written:
        print("      (모두 캐시 적중 — 새로 만든 것 없음)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
