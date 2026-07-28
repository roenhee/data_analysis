"""코어 7축의 이름과 Trino 표현식. DB에 접근하지 않는 순수 함수."""
from __future__ import annotations

CORE_AXIS_NAMES = (
    "period",
    "service_type",
    "os",
    "gender",
    "age_band",
    "daypart",
    "app_version",
)

OS_FAMILIES = ("android", "ios", "windows", "macos")


def _lit(value) -> str:
    """SQL 문자열 리터럴. 단일 인용부호를 이스케이프한다."""
    return "'" + str(value).replace("'", "''") + "'"


def period_expr() -> str:
    return "date_id"


def service_type_expr() -> str:
    return "coalesce(nullif(trim(common.service_type), ''), 'unknown')"


def os_expr() -> str:
    whens = " ".join(
        f"WHEN {_lit(f)} THEN {_lit(f)}" for f in OS_FAMILIES
    )
    return f"CASE lower(coalesce(env.os, '')) {whens} ELSE 'other' END"


def daypart_expr() -> str:
    return "coalesce(nullif(trim(date.daypart), ''), 'unknown')"


def gender_expr(dim_alias: str = "d") -> str:
    return f"coalesce(nullif(trim({dim_alias}.gender), ''), 'unknown')"


def age_band_expr(dim_alias: str = "d") -> str:
    """`service_age_band` 의 `0` 은 원천이 쓰는 '연령 미상' 센티널이다.

    매칭 실패(NULL)와 **같은 `'unknown'` 한 버킷으로 접는다.** 둘을 나누면 스펙이 정의한
    8개 값이 9개가 되고, `age_band='unknown'` 으로 필터하는 소비자가 미상 유저의
    대부분(전체 성연령 테이블의 64%)을 조용히 놓친다. 매칭 여부 자체의 구분은 축이 아니라
    커버리지·`quality` 큐브에서 다룬다.
    """
    col = f"{dim_alias}.service_age_band"
    return (
        f"CASE WHEN {col} IS NULL OR {col} = 0 THEN 'unknown' "
        f"ELSE cast({col} AS varchar) END"
    )


def app_version_expr(versions: list[str]) -> str:
    if not versions:
        return "'other'"
    listed = ", ".join(_lit(v) for v in versions)
    return (
        f"CASE WHEN env.app_version IN ({listed}) "
        f"THEN env.app_version ELSE 'other' END"
    )


def core_axis_selects(versions: list[str], dim_alias: str = "d") -> list[str]:
    """`<expr> AS <axis>` 형태의 SELECT 절 목록. CORE_AXIS_NAMES 순서와 같다."""
    exprs = (
        period_expr(),
        service_type_expr(),
        os_expr(),
        gender_expr(dim_alias),
        age_band_expr(dim_alias),
        daypart_expr(),
        app_version_expr(versions),
    )
    return [f"{e} AS {name}" for e, name in zip(exprs, CORE_AXIS_NAMES)]
