import json

import pytest

from data_layer.sources import SourceDef, load_sources, resolve_auth


def _def(**over):
    base = dict(
        id="events",
        kind="trino",
        host="h",
        port=8443,
        catalog="cat",
        schema="sch",
        table="tbl",
        auth_ref="TIARA",
        column_map={"action_name": "action.name"},
        filters=["action.type IN ('Pageview')"],
    )
    base.update(over)
    return SourceDef(**base)


def test_version_stable_and_sensitive():
    v1 = _def().version()
    v2 = _def().version()
    assert v1 == v2
    assert _def(table="other").version() != v1


def test_load_sources_from_json(tmp_path):
    p = tmp_path / "sources.json"
    p.write_text(
        json.dumps(
            [
                {
                    "id": "events",
                    "kind": "trino",
                    "host": "h",
                    "port": 8443,
                    "catalog": "cat",
                    "schema": "sch",
                    "table": "tbl",
                    "auth_ref": "TIARA",
                    "column_map": {"action_name": "action.name"},
                    "filters": [],
                }
            ]
        )
    )
    srcs = load_sources(p)
    assert set(srcs) == {"events"}
    assert srcs["events"].catalog == "cat"


def test_resolve_auth_reads_env(monkeypatch):
    monkeypatch.setenv("TIARA_ID", "roen-axz")
    monkeypatch.setenv("TIARA_PW", "secret")
    user, pw = resolve_auth(_def())
    assert (user, pw) == ("roen-axz", "secret")


def test_resolve_auth_missing_env_raises(monkeypatch):
    monkeypatch.delenv("TIARA_ID", raising=False)
    with pytest.raises(KeyError):
        resolve_auth(_def())
