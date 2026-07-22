import pandas as pd

from data_layer.enrich import join_dim


def test_join_dim_left_adds_attributes():
    events = pd.DataFrame(
        {"app_user_id": ["u1", "u2", "u3"], "action_name": ["a", "b", "c"]}
    )
    demo = pd.DataFrame(
        {"app_user_id": ["u1", "u2"], "gender": ["F", "M"], "age": [20, 30]}
    )
    out = join_dim(events, demo, key="app_user_id", how="left")
    out = out.sort_values("app_user_id").reset_index(drop=True)
    assert list(out["gender"]) == ["F", "M", None]
    assert len(out) == 3


def test_join_dim_preserves_event_rows():
    events = pd.DataFrame({"app_user_id": ["u1", "u1"], "x": [1, 2]})
    demo = pd.DataFrame({"app_user_id": ["u1"], "gender": ["F"]})
    out = join_dim(events, demo, key="app_user_id", how="left")
    assert len(out) == 2
    assert set(out["gender"]) == {"F"}
