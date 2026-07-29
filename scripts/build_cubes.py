"""큐브 빌드 CLI.

사용:
    build_cubes.py <시작> <끝> <서비스,목록> [--state-dict=<버전>] [--refresh]

예:
    .venv/bin/python scripts/build_cubes.py 2026-07-27 2026-07-27 top,media
    .venv/bin/python scripts/build_cubes.py 2026-07-20 2026-07-26 top,media \
        --state-dict=sd_6738252b8bc0dfd6

`--state-dict` 로 **기존 사전을 재사용**하면 날짜만 덧붙일 수 있다. 없으면 매번
`window` 전체로 사전을 새로 만드는데, 사전 버전이 캐시 키에 들어가므로 기간을 늘리는
순간 **앞서 만든 날짜까지 전부 재빌드된다.** 기간을 나눠 채울 계획이면 첫 실행의
사전 버전을 받아 이후 실행에 넘긴다.

`--refresh` 는 캐시 적중을 무시하고 다시 만든다. 집계 SQL을 고친 뒤에는 캐시 키가
저절로 바뀌므로 보통 필요 없다.

테이블 좌표는 `sources.json` 에서 읽어 빌더에 넘긴다 — 빌더의 기본 상수에 기대지
않으므로 좌표가 바뀌면 쿼리도 같이 바뀐다.
"""
from __future__ import annotations

import sys
from pathlib import Path

# `pythonpath = .` 는 pytest 에만 적용된다. 스크립트로 직접 돌 때도 리포 루트를 찾게 한다.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from analytics.cube.builder import SOURCES_PATH, build_cubes, build_state_dict  # noqa: E402
from analytics.cube.state_dict import load_state_dict  # noqa: E402
from data_layer.config import Config  # noqa: E402
from data_layer.sources import load_sources  # noqa: E402


class UsageError(ValueError):
    """인자를 해석할 수 없다."""


def parse_args(argv: list[str]) -> dict:
    """`argv[1:]` 를 해석한다. 위치 인자 3개 + 선택 플래그."""
    positional: list[str] = []
    state_dict_version: str | None = None
    refresh = False
    for arg in argv[1:]:
        if arg == "--refresh":
            refresh = True
        elif arg.startswith("--state-dict="):
            state_dict_version = arg.split("=", 1)[1]
            if not state_dict_version:
                raise UsageError("--state-dict= 뒤에 버전이 없다")
        elif arg.startswith("--"):
            raise UsageError(f"모르는 플래그: {arg}")
        else:
            positional.append(arg)
    if len(positional) != 3:
        raise UsageError(
            f"위치 인자는 <시작> <끝> <서비스> 3개여야 한다 (받은 것: {len(positional)})"
        )
    start, end, services_csv = positional
    services = [s.strip() for s in services_csv.split(",") if s.strip()]
    if not services:
        raise UsageError("서비스 목록이 비었다")
    return dict(
        start=start, end=end, services=services,
        state_dict_version=state_dict_version, refresh=refresh,
    )


def main(argv: list[str]) -> int:
    try:
        args = parse_args(argv)
    except UsageError as e:
        print(f"오류: {e}\n")
        print(__doc__)
        return 2

    config = Config.from_env()
    config.ensure_dirs()
    sources = load_sources(Path(SOURCES_PATH))
    events = sources["events"]
    demography = sources["demography"]
    start, end, services = args["start"], args["end"], args["services"]

    if args["state_dict_version"]:
        sd = load_state_dict(config, args["state_dict_version"])
        print(f"[1/2] state 사전 재사용 {sd.version()}")
    else:
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
        refresh=args["refresh"],
        events_table=events.qualified_name(),
        demography_table=demography.qualified_name(),
    )
    for p in written:
        size_kb = p.stat().st_size / 1024
        print(f"      {p}  ({size_kb:,.0f} KB)")
    if not written:
        print("      (모두 캐시 적중 — 새로 만든 것 없음)")
    print(f"\n날짜를 덧붙이려면: --state-dict={sd.version()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
