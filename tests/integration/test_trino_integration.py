import os

import pytest

from data_layer.connection import connect
from data_layer.sources import SourceDef

pytestmark = pytest.mark.integration

EVENTS_SOURCE = SourceDef(
    id="events",
    kind="trino",
    host="hadoop-rabbit-trino.onkakao.net",
    port=8443,
    catalog="hadoop_rabbit_iceberg",
    schema="axz_da",
    table="all_tiara_i",
    auth_ref="TIARA",
)


@pytest.fixture(autouse=True)
def _require_creds():
    if not (os.environ.get("TIARA_ID") and os.environ.get("TIARA_PW")):
        pytest.skip("TIARA_ID/TIARA_PW not set — skipping live Trino test")


def test_connect_and_trivial_query():
    conn = connect(EVENTS_SOURCE)
    try:
        cur = conn.cursor()
        cur.execute("SELECT 1")
        assert cur.fetchone()[0] == 1
    finally:
        conn.close()


def test_show_tables_accessible():
    conn = connect(EVENTS_SOURCE)
    try:
        cur = conn.cursor()
        cur.execute("SHOW TABLES FROM hadoop_rabbit_iceberg.axz_da")
        rows = cur.fetchall()
        assert isinstance(rows, list)
    finally:
        conn.close()
