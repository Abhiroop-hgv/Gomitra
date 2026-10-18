"""Composition root: the shared adapters the services use. Created once, at import time.

store  : documents (Firestore in the cloud, in memory for tests)          infra/store.py
infer  : the model service (Vertex AI endpoint, Cloud Run or in-process)   infra/inference.py
kb     : the vet knowledge base (embeddings + search + grounded answers)   services/kb.py
Tests replace behaviour by choosing the in-memory store (STORE=memory) and the in-process models (INFER_BACKEND=local).
"""
from gomitra.infra.inference import Infer
from gomitra.infra.store import make_store
from gomitra.services.kb import KB

store = make_store()
infer = Infer()
kb = KB(store)
