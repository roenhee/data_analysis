import json
from pathlib import Path

from data_layer.config_artifacts import load_dictionary, events_source_from_json
from data_layer.sources import load_sources


def test_events_source_from_examples():
    src = events_source_from_json(Path("examples/config/sources.json"), "events")
    assert src.catalog == "bigdata_omega_common_iceberg"
    assert src.schema == "axz_tiara"
    assert src.table == "all_tiara_n"
    assert src.auth_ref == "TIARA"
    assert "action_name" in src.column_map
    assert any("uuid" in f or "suid" in f for f in src.filters)


def test_load_dictionary(tmp_path):
    p = tmp_path / "dict.json"
    p.write_text(json.dumps({"cutoff": 0.95, "vocabulary": ["A"], "mapping": {"A": "A"}}))
    d = load_dictionary(p)
    assert d["cutoff"] == 0.95
    assert d["mapping"]["A"] == "A"


def test_events_source_points_at_deidentified_table():
    srcs = load_sources(Path("examples/config/sources.json"))
    src = srcs["events"]
    assert src.table == "all_tiara_n"
    assert src.catalog == "bigdata_omega_common_iceberg"
    assert src.schema == "axz_tiara"
    # 비식별 테이블의 식별자
    assert src.column_map["uuid"] == "user.uuid"
    assert src.column_map["suid"] == "user.suid"
    # 파티션 컬럼이 매핑에 있어야 프루닝 SQL을 만들 수 있다
    assert src.column_map["date_id"] == "date_id"
    assert src.column_map["service_code"] == "c_service_code"
    # date.day 는 '요일'이므로 날짜 축으로 쓰면 안 된다
    assert "day" not in src.column_map


def test_demography_source_is_declared():
    srcs = load_sources(Path("examples/config/sources.json"))
    dem = srcs["demography"]
    assert dem.catalog == "hadoop_doopey"
    assert dem.schema == "target_subcom"
    assert dem.table == "tb_axz_demography_uuid_v2"
    assert dem.column_map["uuid"] == "uuid"
    assert dem.column_map["gender"] == "gender"
    assert dem.column_map["age_band"] == "service_age_band"
