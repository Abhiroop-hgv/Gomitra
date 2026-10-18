"""infra/store.py: the document store (in-memory implementation; Firestore has the same methods)."""
import pytest

from gomitra.infra import store as store_mod


@pytest.fixture
def s():
    return store_mod.Memory()


def test_put_get_update_delete(s):
    s.put("cows", "a", {"name": "Gauri", "alert": False})
    assert s.get("cows", "a") == {"name": "Gauri", "alert": False}
    s.update("cows", "a", {"alert": True, "kind": "lumpy"})
    assert s.get("cows", "a") == {"name": "Gauri", "alert": True, "kind": "lumpy"}
    s.delete("cows", "a")
    assert s.get("cows", "a") is None
    s.delete("cows", "missing")                    # deleting nothing is fine


def test_a_stored_document_is_a_copy(s):
    doc = {"n": 1}
    s.put("c", "a", doc)
    doc["n"] = 2
    got = s.get("c", "a"); got["n"] = 3
    assert s.get("c", "a") == {"n": 1}


def test_list_includes_the_ids(s):
    s.put("c", "a", {"x": 1}); s.put("c", "b", {"x": 2})
    assert sorted((d["id"], d["x"]) for d in s.list("c")) == [("a", 1), ("b", 2)]
    assert s.list("empty") == []


def test_list_where_filters_on_one_field(s):
    s.put("log", "1", {"cow": "a"}); s.put("log", "2", {"cow": "b"}); s.put("log", "3", {"cow": "a"})
    assert sorted(d["id"] for d in s.list_where("log", "cow", "a")) == ["1", "3"]


def test_batch_helpers(s):
    s.put_many("c", [("a", {"x": 1}), ("b", {"x": 2})])
    assert len(s.list("c")) == 2
    s.delete_many("c", ["a", "b"])
    assert s.list("c") == []


def test_make_store_is_in_memory_when_asked(monkeypatch):
    monkeypatch.setenv("STORE", "memory")
    assert isinstance(store_mod.make_store(), store_mod.Memory)
