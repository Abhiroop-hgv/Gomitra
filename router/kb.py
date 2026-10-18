"""Vet knowledge base: PDFs/text -> chunks -> multilingual embeddings (Vertex AI) -> Firestore -> search -> grounded answers.

Small on purpose: a few hundred chunks fit in memory, so search is a plain cosine over a cached matrix. If the library
grows, swap search() for Vertex AI Search or Firestore vector search; the rest of the app does not change.
A question in Telugu can match an English passage because the embedding model is multilingual.
"""
import hashlib
import io
import json
import os
import re

import numpy as np

import gmtrace as trace

PROJECT = os.getenv("PROJECT", "cattle-id-511705")
EMBED_MODEL = os.getenv("EMBED_MODEL", "gemini-embedding-001")
EMBED_LOCATION = os.getenv("EMBED_LOCATION", "us-central1")
EMBED_DIM = 768
CHUNK_WORDS, OVERLAP = 180, 30
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
GEMINI_LOCATION = os.getenv("GEMINI_LOCATION", "global")
COL = "kb_chunks"
MIN_SCORE = 0.45          # below this a passage is not considered relevant


def _client(location):
    from google import genai
    from google.genai import types
    return genai.Client(vertexai=True, project=PROJECT, location=location,
                        http_options=types.HttpOptions(timeout=40000)), types


def embed(texts, query=False):
    """list[str] -> (n, EMBED_DIM) unit vectors. EMBED_BACKEND=fake gives deterministic vectors for offline tests."""
    if os.getenv("EMBED_BACKEND") == "fake":
        out = np.zeros((len(texts), EMBED_DIM), np.float32)
        for i, t in enumerate(texts):
            for w in re.findall(r"\w+", t.lower()):
                out[i, int(hashlib.md5(w.encode()).hexdigest(), 16) % EMBED_DIM] += 1
        return out / np.maximum(np.linalg.norm(out, axis=1, keepdims=True), 1e-9)
    client, types = _client(EMBED_LOCATION)
    rows = []
    for i in range(0, len(texts), 50):
        with trace.step("Vertex AI embeddings", f"{EMBED_MODEL}, multilingual vet-note search"):
            r = client.models.embed_content(
                model=EMBED_MODEL, contents=texts[i:i + 50],
                config=types.EmbedContentConfig(task_type="RETRIEVAL_QUERY" if query else "RETRIEVAL_DOCUMENT",
                                                output_dimensionality=EMBED_DIM))
        rows += [e.values for e in r.embeddings]
    m = np.array(rows, np.float32)
    return m / np.maximum(np.linalg.norm(m, axis=1, keepdims=True), 1e-9)


def pdf_text(data: bytes) -> str:
    from pypdf import PdfReader
    return "\n".join((p.extract_text() or "") for p in PdfReader(io.BytesIO(data)).pages)


def chunks(text):
    words = text.split()
    step = CHUNK_WORDS - OVERLAP
    return [" ".join(words[i:i + CHUNK_WORDS]) for i in range(0, max(len(words), 1), step) if words[i:i + CHUNK_WORDS]]


class KB:
    def __init__(self, store):
        self.store, self._cache = store, None

    def add(self, source, text):
        """Index one document; returns the number of chunks. Re-adding a source replaces its old chunks."""
        for c in self.store.list(COL):
            if c.get("source") == source:
                self.store.delete(COL, c["id"])
        parts = chunks(re.sub(r"\s+", " ", text))
        if not parts:
            return 0
        vecs = embed(parts)
        for i, (t, v) in enumerate(zip(parts, vecs)):
            self.store.put(COL, hashlib.md5(f"{source}:{i}".encode()).hexdigest(),
                           {"source": source, "n": i, "text": t, "emb": [float(x) for x in v]})
        self._cache = None
        return len(parts)

    def remove(self, source):
        n = 0
        for c in self.store.list(COL):
            if c.get("source") == source:
                self.store.delete(COL, c["id"]); n += 1
        self._cache = None
        return n

    def _load(self):
        if self._cache is None:
            rows = self.store.list(COL)
            self._cache = (rows, np.array([r["emb"] for r in rows], np.float32) if rows else np.zeros((0, EMBED_DIM)))
        return self._cache

    def sources(self):
        rows, _ = self._load()
        out = {}
        for r in rows:
            out[r["source"]] = out.get(r["source"], 0) + 1
        return out

    def search(self, query, k=4):
        rows, m = self._load()
        if not len(rows):
            return []
        s = m @ embed([query], query=True)[0]
        return [{"source": rows[i]["source"], "text": rows[i]["text"], "score": round(float(s[i]), 3)}
                for i in np.argsort(-s)[:k] if s[i] >= MIN_SCORE]

    def answer(self, question, lang="en", cow=None):
        """Grounded answer in the farmer's language. -> {"answer", "sources": [...], "grounded": bool}"""
        hits = self.search(question + (f" ({cow})" if cow else ""))
        names = {"en": "English", "hi": "Hindi (Devanagari script)", "te": "Telugu (Telugu script)"}[lang]
        if not hits:
            msg = {"en": "I could not find this in the vet documents I have. Please ask your vet.",
                   "hi": "यह जानकारी मेरे पशु-चिकित्सा दस्तावेज़ों में नहीं मिली। कृपया अपने पशु चिकित्सक से पूछें।",
                   "te": "ఈ సమాచారం నా పశు వైద్య పత్రాలలో కనిపించలేదు. దయచేసి మీ పశు వైద్యుడిని అడగండి."}[lang]
            return {"answer": msg, "sources": [], "grounded": False}
        ctx = "\n\n".join(f"[{i + 1}] ({h['source']}) {h['text']}" for i, h in enumerate(hits))
        prompt = f"""You are GoMitra, a helper for Indian dairy farmers. Answer ONLY from the passages below.
If they do not contain the answer, say you do not know and tell the farmer to call a vet.
Rules: short simple sentences in {names}; give clear next steps; never give drug names or doses;
for anything serious, contagious or getting worse, tell the farmer to call a vet; do not diagnose.
End with the sources you used, like: Source: [1].

Passages:
{ctx}

Farmer's question: {question}"""
        client, types = _client(GEMINI_LOCATION)
        with trace.step("Gemini on Vertex AI", f"{GEMINI_MODEL}, answer from the retrieved vet-note passages"):
            r = client.models.generate_content(model=GEMINI_MODEL, contents=prompt,
                                               config=types.GenerateContentConfig(temperature=0.2))
        return {"answer": r.text.strip(), "sources": sorted({h["source"] for h in hits}), "grounded": True}
