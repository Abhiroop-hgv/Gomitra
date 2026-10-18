"""Which registered cow is this? Face matching by embedding, ear-tag fallback, and finding the face inside a cow's box.

Pure logic: it works on the dicts the cow-face model returns and the cows' stored embeddings.
"""
import numpy as np

from gomitra import config
from gomitra.domain import rules


def match_face(ident, cows, threshold=None):
    """Best registered cow for the sharpest face in an identify result -> (cow, score) or (None, best score)."""
    threshold = config.FACE_MATCH if threshold is None else threshold
    face = rules.best_face(ident)
    if not face:
        return None, 0.0
    q = np.array(face["embedding"], np.float32)
    best, best_s = None, 0.0
    for c in cows:
        for e in c.get("embeddings") or []:
            s = float(np.dot(q, np.array(e["v"], np.float32)))
            if s > best_s:
                best, best_s = c, s
    return (best, best_s) if best_s >= threshold else (None, best_s)


def match_tag(ident, cows):
    """Fallback: an ear-tag number read by OCR that equals a registered tag."""
    for f in (ident or {}).get("faces", []):
        for t in f.get("tags", []):
            n = (t.get("read") or {}).get("number")
            if n:
                for c in cows:
                    if c.get("tag", "").lstrip("0") == n.lstrip("0"):
                        return c
    return None


def face_in_box(ident, box):
    """The usable face whose centre lies inside a cow box (CCTV frames can hold several cows)."""
    x1, y1, x2, y2 = box
    for f in (ident or {}).get("faces", []):
        fx, fy = (f["box"][0] + f["box"][2]) / 2, (f["box"][1] + f["box"][3]) / 2
        if f.get("usable") and x1 <= fx <= x2 and y1 <= fy <= y2:
            return {"faces": [f]}
    return None
