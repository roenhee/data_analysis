from trino.auth import BasicAuthentication

from data_layer.connection import trino_connect_params
from data_layer.sources import SourceDef


def _src():
    return SourceDef(
        id="events",
        kind="trino",
        host="hadoop-rabbit-trino.onkakao.net",
        port=8443,
        catalog="hadoop_rabbit_iceberg",
        schema="axz_da",
        table="all_tiara_i",
        auth_ref="TIARA",
    )


def test_connect_params_shape():
    p = trino_connect_params(_src(), "roen-axz", "secret")
    assert p["host"] == "hadoop-rabbit-trino.onkakao.net"
    assert p["port"] == 8443
    assert p["user"] == "roen-axz"
    assert p["catalog"] == "hadoop_rabbit_iceberg"
    assert p["schema"] == "axz_da"
    assert p["http_scheme"] == "https"
    assert isinstance(p["auth"], BasicAuthentication)
