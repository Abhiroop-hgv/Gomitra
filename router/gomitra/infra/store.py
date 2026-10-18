"""Tiny document store: Firestore in the cloud, a dict in memory for laptop tests (STORE=memory).

Collections: cows, observations, alerts, audio_events. Firestore cannot hold arrays inside arrays,
so embeddings are saved as a list of {"v": [...]} maps (see main.py).
"""
import os
import threading

from gomitra.core import tracing as trace
class Memory:
    def __init__(self):
        self.d, self.lock = {}, threading.Lock()

    def put(self, col, doc_id, data):
        with self.lock:
            self.d.setdefault(col, {})[doc_id] = dict(data)

    def update(self, col, doc_id, data):
        with self.lock:
            self.d.setdefault(col, {}).setdefault(doc_id, {}).update(data)

    def get(self, col, doc_id):
        return dict(self.d.get(col, {}).get(doc_id) or {}) or None

    def list(self, col):
        return [dict(v, id=k) for k, v in self.d.get(col, {}).items()]

    def delete(self, col, doc_id):
        self.d.get(col, {}).pop(doc_id, None)

    def list_where(self, col, field, value):
        return [v for v in self.list(col) if v.get(field) == value]

    def put_many(self, col, items):
        """items: [(doc_id, data)]"""
        for i, d in items:
            self.put(col, i, d)

    def delete_many(self, col, ids):
        for i in ids:
            self.delete(col, i)


class Firestore:
    _TRACE = ("Firestore", "{n} reads/writes, asia-south1")       # shown in "Behind this result", one merged line

    def __init__(self, project):
        from google.cloud import firestore
        self.db = firestore.Client(project=project)

    def put(self, col, doc_id, data):
        with trace.step(*self._TRACE, aggregate=True):
            self.db.collection(col).document(doc_id).set(data)

    def update(self, col, doc_id, data):
        with trace.step(*self._TRACE, aggregate=True):
            self.db.collection(col).document(doc_id).set(data, merge=True)

    def get(self, col, doc_id):
        with trace.step(*self._TRACE, aggregate=True):
            s = self.db.collection(col).document(doc_id).get()
        return s.to_dict() if s.exists else None

    def list(self, col):
        with trace.step(*self._TRACE, aggregate=True):
            return [dict(s.to_dict(), id=s.id) for s in self.db.collection(col).stream()]

    def delete(self, col, doc_id):
        with trace.step(*self._TRACE, aggregate=True):
            self.db.collection(col).document(doc_id).delete()

    def list_where(self, col, field, value):
        from google.cloud.firestore_v1.base_query import FieldFilter
        with trace.step(*self._TRACE, aggregate=True):
            q = self.db.collection(col).where(filter=FieldFilter(field, "==", value))
            return [dict(s.to_dict(), id=s.id) for s in q.stream()]

    def _batched(self, ops):
        for i in range(0, len(ops), 400):
            b = self.db.batch()
            for op in ops[i:i + 400]:
                op(b)
            b.commit()

    def put_many(self, col, items):
        self._batched([(lambda b, i=i, d=d: b.set(self.db.collection(col).document(i), d)) for i, d in items])

    def delete_many(self, col, ids):
        self._batched([(lambda b, i=i: b.delete(self.db.collection(col).document(i))) for i in ids])


def make_store():
    if os.getenv("STORE", "firestore") == "memory":
        return Memory()
    return Firestore(os.getenv("PROJECT", "cattle-id-511705"))
