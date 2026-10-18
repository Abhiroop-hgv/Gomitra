"""Per-request trace: which Google service did each step of a request, and how long it really took.

The router wraps every call to a model, Gemini, the embeddings or the pose service in `with step(...)`, and counts
Firestore reads and writes. The endpoints return the list so the app can show "Behind this result". The times are measured,
not written by hand. If a step fails or falls back, the step says so.
"""
import contextvars
import time

_cur = contextvars.ContextVar("gomitra_trace", default=None)


def start():
    """Begin a trace for this request (a nested call keeps the trace its caller started)."""
    if _cur.get() is None:
        _cur.set({"steps": [], "agg": {}})


def get():
    t = _cur.get()
    if t is None:
        return []
    out = list(t["steps"])
    for (service, detail), (n, ms) in t["agg"].items():
        out.append({"service": service, "detail": detail.format(n=n), "ms": round(ms)})
    return out


class step:
    """with step("Gemini on Vertex AI", "gemini-2.5-flash") as s: ...   (s.detail can be changed before the block ends)
    aggregate=True merges repeated calls of the same kind into one line (used for Firestore); {n} in detail is the count."""

    def __init__(self, service, detail, aggregate=False):
        self.service, self.detail, self.aggregate = service, detail, aggregate

    def __enter__(self):
        self._t = time.perf_counter()
        return self

    def __exit__(self, exc_type, exc, tb):
        t = _cur.get()
        if t is None:
            return False
        ms = (time.perf_counter() - self._t) * 1000
        if exc_type is not None:
            self.detail += f" (failed: {exc_type.__name__})"
        if self.aggregate:
            key = (self.service, self.detail)
            n, total = t["agg"].get(key, (0, 0.0))
            t["agg"][key] = (n + 1, total + ms)
        else:
            t["steps"].append({"service": self.service, "detail": self.detail, "ms": round(ms)})
        return False
