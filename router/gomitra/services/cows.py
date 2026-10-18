"""Cows: registering, reading and clearing a cow's record. A cow is one Firestore document in `cows`."""
import re

from gomitra.context import infer, store
from gomitra.core.util import data_url, now, read_image
from gomitra.domain import rules
from gomitra.errors import BadRequest, NotFound
from gomitra.infra import inference as inf


def public(c):
    """What the app may see: everything except embeddings and raw history."""
    keep = ("id", "name", "tag", "breed", "age", "camera", "alert", "kind", "severity", "short", "msg", "source",
            "last_seen", "tile", "scene", "box", "demo", "signals", "faces")
    out = {k: c.get(k) for k in keep}
    out["alert"] = bool(c.get("alert"))
    out["registered_faces"] = len(c.get("embeddings") or [])
    return out


def get_cow(cid):
    c = store.get("cows", cid)
    if not c:
        raise NotFound("cow not found")
    return dict(c, id=cid)


def all_cows():
    return [dict(c) for c in store.list("cows")]


def list_public():
    """Cows needing attention first, then by name."""
    out = [public(c) for c in all_cows()]
    out.sort(key=lambda c: (not c["alert"], c["name"]))
    return out


def register(name, tag, breed, age, photos):
    """Register a cow from up to four photos (front, left, right, back as base64/data URLs) and her ear tag.
    The cow-face model gives one embedding per photo that shows a usable face; those are what later frames are matched to."""
    tag = tag.strip()
    if not tag:
        raise BadRequest("ear tag required")
    jpegs = {k: inf.shrink_jpeg(read_image(v)) for k, v in photos.items() if v}
    keys = list(jpegs)
    preds = infer.predict([{"task": "identify", "image_b64": inf.b64(jpegs[k])} for k in keys]) if keys else []
    embs, faces = [], {}
    for k, p in zip(keys, preds):
        f = rules.best_face(p)
        faces[k] = bool(f)
        if f:
            embs.append({"v": f["embedding"]})
    cid = re.sub(r"[^a-z0-9]+", "-", (name or "cow").lower()).strip("-") + "-" + tag
    first = jpegs.get("front") or (jpegs[keys[0]] if keys else None)
    doc = {"name": name.strip() or f"Cow {tag}", "tag": tag, "breed": breed, "age": age, "camera": "Camera 1",
           "alert": False, "kind": None, "history": [], "last_seen": now(), "embeddings": embs, "faces": faces,
           "tile": data_url(inf.shrink_jpeg(first, 360, 80)) if first else None,
           "scene": data_url(inf.shrink_jpeg(first, 720, 80)) if first else None, "created": now()}
    store.put("cows", cid, doc)
    return {"cow": public(dict(doc, id=cid)), "faces_found": sum(faces.values()),
            "warning": None if embs else "No cow face was found in the photos, so the cow can only be matched by ear tag."}


def resolve(cid):
    """The farmer has checked the cow: clear her alert, signals and finding history."""
    get_cow(cid)
    store.update("cows", cid, {"alert": False, "kind": None, "severity": None, "short": None, "msg": None,
                               "box": None, "signals": {}, "history": []})


def remove(cid):
    store.delete("cows", cid)
