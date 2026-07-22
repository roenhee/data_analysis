from data_layer.cleanup import drop_temp_tables, filter_prefixed


def test_filter_prefixed():
    names = ["roen_tmp_a", "roen_tmp_b", "other", "roen_keep"]
    assert filter_prefixed(names, "roen_tmp_") == ["roen_tmp_a", "roen_tmp_b"]


def test_drop_temp_tables_issues_drops_via_fake_conn():
    executed = []

    class FakeCursor:
        def execute(self, sql):
            executed.append(sql)
            self._rows = [("roen_tmp_a",), ("roen_tmp_b",), ("keep",)]

        def fetchall(self):
            return self._rows

    class FakeConn:
        def cursor(self):
            return FakeCursor()

    dropped = drop_temp_tables(
        FakeConn(), catalog="cat", schema="sch", prefix="roen_tmp_"
    )
    assert dropped == ["roen_tmp_a", "roen_tmp_b"]
    assert any("DROP TABLE" in s and "roen_tmp_a" in s for s in executed)
    assert not any("keep" in s and "DROP" in s for s in executed)
