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
    return f"coalesce(cast({dim_alias}.service_age_band AS varchar), 'unknown')"


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
