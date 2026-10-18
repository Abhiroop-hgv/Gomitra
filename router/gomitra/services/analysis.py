"""Analyse a picture: skin screening + cow recognition + alert rules.

mode "photo": a farmer's upload; the whole image is classified.   mode "cctv": a camera frame; cows are found first, each is checked.
"""
import uuid

import cv2
import numpy as np

from gomitra.context import infer, store
from gomitra.core import tracing as trace
from gomitra.core.util import data_url, now, read_image
from gomitra.domain import matching, rules
from gomitra.errors import UpstreamError
from gomitra.infra import inference as inf
from gomitra.services import messages
from gomitra.services.alerts import raise_alert
from gomitra.services.cows import all_cows, get_cow, public


def _items(lumpy, ident, jpeg, cctv):
    """One entry per cow seen: skin result, box (as fractions of the picture, so any screen can draw it), face result."""
    if not cctv:
        ph = lumpy["photo"]
        return [{"usable": ph["usable"], "reason": ph.get("reason", ""), "probs": ph.get("probs"),
                 "box": None, "ident": ident, "cows_detected": ph.get("cows_detected")}]
    H, W = cv2.imdecode(np.frombuffer(jpeg, np.uint8), cv2.IMREAD_COLOR).shape[:2]
    out = []
    for c in lumpy["cows"]:
        x1, y1, x2, y2 = c["box"]
        out.append({"usable": c["usable"], "reason": c.get("reason", ""), "probs": c.get("probs"),
                    "box": [round(x1 / W, 4), round(y1 / H, 4), round(x2 / W, 4), round(y2 / H, 4)],
                    "ident": matching.face_in_box(ident, c["box"])})
    return out


def analyze(image, mode="photo", camera="Camera 1", cow_id=None, read_tags=False):
    trace.start()
    cctv = mode == "cctv"
    jpeg = inf.shrink_jpeg(read_image(image))
    lumpy, ident = infer.vision(jpeg, cctv=cctv, read_tags=False)
    for p in (lumpy, ident):
        if p.get("error"):
            raise UpstreamError(p["error"])
    registered = all_cows()
    scene = inf.shrink_jpeg(jpeg, 720, 80)
    results = []
    for it in _items(lumpy, ident, jpeg, cctv):
        cow_doc, score, method = None, 0.0, None
        if cow_id:
            cow_doc, method = get_cow(cow_id), "chosen"
        elif it["ident"]:
            cow_doc, score = matching.match_face(it["ident"], registered)
            method = "face" if cow_doc else None
            if not cow_doc and (read_tags or ident.get("tags_in_frame")):
                ocr = infer.predict([{"task": "identify", "image_b64": inf.b64(jpeg), "read_tags": True}])[0]
                cow_doc = matching.match_tag(ocr, registered)
                method = "ear tag" if cow_doc else None
        finding = rules.skin_finding(it["probs"]) if it["usable"] else None
        res = {"usable": it["usable"], "reason": it["reason"], "probs": it["probs"], "box": it["box"],
               "finding": finding, "cow": None, "match": {"method": method, "score": round(score, 3)} if method else None,
               "alert": False, "message": None}
        if cow_doc:
            _record(cow_doc, it, finding, cctv, scene, camera, mode, res)
            res["cow"] = public(get_cow(cow_doc["id"]))
        elif finding and it["usable"]:
            res["message"] = messages.template(finding["kind"], "this cow")      # not registered: say it, store nothing
        results.append(res)
    return {"mode": mode, "faces_in_frame": len(ident.get("faces", [])), "results": results, "trace": trace.get()}


def _record(cow_doc, it, finding, cctv, scene, camera, mode, res):
    """Save the sighting on the cow, and raise an alert when the finding is confirmed."""
    cid = cow_doc["id"]
    hist = list(cow_doc.get("history") or [])
    kind = finding["kind"] if finding else "ok"
    if not it["usable"]:
        return
    confirmed = bool(finding) and rules.confirmed(hist, kind, cctv)
    store.update("cows", cid, {"history": (hist + [kind])[-10:], "last_seen": now()})
    if confirmed:
        upd = raise_alert(cow_doc, finding, scene, it["box"], camera)
        store.update("cows", cid, upd)
        res["alert"], res["message"] = True, upd.get("msg") or cow_doc.get("msg")
    elif not finding:
        store.update("cows", cid, {"scene": data_url(scene), "last_seen": now(),
                                   "signals": dict(cow_doc.get("signals") or {}, skin="ok")})
    store.put("observations", uuid.uuid4().hex, {"cow_id": cid, "ts": now(), "kind": kind, "camera": camera,
                                                 "p": (finding or {}).get("p"), "mode": mode})
