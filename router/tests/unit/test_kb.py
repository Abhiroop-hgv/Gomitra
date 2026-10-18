"""services/kb.py: the vet knowledge base: split documents, embed (fake embeddings in tests), search, remove."""
import numpy as np
import pytest

from gomitra.infra import store as store_mod
from gomitra.services import kb as kb_mod


@pytest.fixture
def kb():
    return kb_mod.KB(store_mod.Memory())


def test_chunks_overlap_and_cover_the_text():
    text = " ".join(f"w{i}" for i in range(500))
    parts = kb_mod.chunks(text)
    assert all(len(p.split()) <= kb_mod.CHUNK_WORDS for p in parts)
    assert parts[0].split()[0] == "w0" and parts[-1].split()[-1] == "w499"
    assert parts[1].split()[0] == f"w{kb_mod.CHUNK_WORDS - kb_mod.OVERLAP}"          # the next piece starts inside the last one


def test_short_and_empty_text():
    assert kb_mod.chunks("one two three") == ["one two three"]
    assert kb_mod.chunks("") == []


def test_fake_embeddings_are_deterministic_unit_vectors_and_similar_texts_are_close():
    a, b, c = kb_mod.embed(["lumpy skin disease spreads by flies", "lumpy skin disease and flies", "milk price today"])
    assert np.allclose(np.linalg.norm(a), 1) and np.allclose(kb_mod.embed(["lumpy skin disease spreads by flies"])[0], a)
    assert a @ b > a @ c


def test_add_search_and_remove(kb):
    assert kb.add("lumpy notes", "Lumpy skin disease spreads by biting flies. Isolate sick cattle and call the vet.") == 1
    kb.add("fmd notes", "Foot and mouth disease causes blisters in the mouth and on the feet. Do not move the animal.")
    assert kb.sources() == {"lumpy notes": 1, "fmd notes": 1}
    top = kb.search("lumpy skin disease biting flies")[0]
    assert top["source"] == "lumpy notes" and top["score"] > kb_mod.MIN_SCORE
    assert kb.remove("lumpy notes") == 1 and "lumpy notes" not in kb.sources()


def test_adding_a_source_again_replaces_its_old_pieces(kb):
    kb.add("doc", "first version about bloat")
    kb.add("doc", "second version about mastitis")
    assert kb.sources() == {"doc": 1} and "mastitis" in kb.search("mastitis")[0]["text"]


def test_an_unrelated_question_finds_nothing_and_the_answer_says_so(kb):
    kb.add("doc", "Lumpy skin disease spreads by biting flies.")
    assert kb.search("zzzz qqqq") == []
    out = kb.answer("zzzz qqqq", "hi")
    assert out["grounded"] is False and out["sources"] == [] and "पशु चिकित्सक" in out["answer"]


def test_empty_library_returns_no_passages(kb):
    assert kb.search("anything") == [] and kb.sources() == {}
