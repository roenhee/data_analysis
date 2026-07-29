"""결과에 항상 동봉하는 맥락.

스펙: 커버리지 / 성연령 매칭률 / 품질 경고 / state 사전 버전 / 비교 안전성.
이게 없으면 소비자가 커버리지 57% 짜리 체류를 전수로 읽는다.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # 순환 임포트를 피하고 런타임 의존도 만들지 않는다.
    from analytics.metrics.load import LoadedCube


@dataclass(frozen=True)
class Envelope:
    """지표 프레임과 함께 다니는 맥락."""

    state_dict_version: str
    # 큐브가 어떤 서비스 범위로 빌드됐는지. 세션의 44.7% 가 여러 서비스에 걸쳐
    # `service_code` 를 세션 큐브 축으로 둘 수 없으므로, 범위는 여기에만 있다.
    services: list[str]
    requested_dates: list[str]
    present_dates: list[str]
    coverage: dict[str, float] = field(default_factory=dict)
    warnings: list[dict] = field(default_factory=list)

    @classmethod
    def for_cube(
        cls,
        loaded: "LoadedCube",
        state_dict_version: str,
        services: list[str],
        coverage: dict[str, float] | None = None,
        warnings: list[dict] | None = None,
    ) -> "Envelope":
        """`LoadedCube` 의 날짜 장부를 그대로 물려받는다."""
        return cls(
            state_dict_version=state_dict_version,
            services=list(services),
            requested_dates=list(loaded.requested_dates),
            present_dates=list(loaded.present_dates),
            coverage=dict(coverage or {}),
            warnings=list(warnings or []),
        )

    @property
    def missing_dates(self) -> list[str]:
        present = set(self.present_dates)
        return [d for d in self.requested_dates if d not in present]

    def as_dict(self) -> dict:
        return {
            "state_dict_version": self.state_dict_version,
            "services": list(self.services),
            "requested_dates": list(self.requested_dates),
            "present_dates": list(self.present_dates),
            "missing_dates": self.missing_dates,
            "is_complete": not self.missing_dates,
            "coverage": dict(self.coverage),
            "warnings": list(self.warnings),
        }


def quality_warnings(quality_cube, thresholds: dict[str, float]) -> list[dict]:
    """`violated / total` 이 임계치를 넘은 검사만 경고로 낸다.

    막지 않고 경고만 한다 — 스펙의 "막을 것과 경고할 것을 구분한다" 원칙이다.
    계산이 틀리게 되는 것(uv 합산, 부분 빌드)은 막고, 해석에 주의가 필요한
    것(커버리지·로깅 편차)은 정보를 주고 통과시킨다.
    """
    out = []
    for row in quality_cube.itertuples():
        limit = thresholds.get(row.check_name)
        if limit is None or row.total <= 0:
            continue
        ratio = row.violated / row.total
        if ratio > limit:
            out.append(
                {
                    "check_name": row.check_name,
                    "service_code": row.service_code,
                    "app_version": row.app_version,
                    "ratio": float(ratio),
                    "threshold": float(limit),
                }
            )
    return out
