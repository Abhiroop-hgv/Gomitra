"""GoMitra router: the brain between the Pi / farmer app and the models.

Runs on Cloud Run. Calls the model container (Vertex AI or Cloud Run), keeps cows and alerts in Firestore,
applies the alert rules, asks Gemini for the farmer message and answers questions from the vet documents.
"""
import base64
import hashlib
import logging
import os
import random
import re
import time
import uuid

import cv2
import numpy as np
from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import agent
import gait
import gmtrace as trace
import infer as infer_mod
import messages
import report
import rules
import suspects
import trends
from kb import KB
from store import make_store

HERE = os.path.dirname(os.path.abspath(__file__))
ADMIN_KEY = os.getenv("ADMIN_KEY", "")
FACE_MATCH = 0.69            # cosine threshold from the cattle_id repo (1% false accepts on close-ups); retune on real data
MAX_BYTES = 8_000_000

app = FastAPI(title="GoMitra router")
store = make_store()
infer = infer_mod.Infer()
kb = KB(store)


# ------------------------------------------------------------------------------------------------ abuse guard
# The app is public so the jury can try it, and every call below costs money (models, Gemini). Each visitor address gets
# a per-minute allowance per kind of call. Counts live in this instance's memory, so they are a brake, not a hard limit.
LIMITS = [("/api/ingest", 90), ("/api/warmup", 6), ("/api/posture", 20), ("/api/analyze", 30), ("/api/audio", 30), ("/api/ask", 30), ("/report", 15), ("/api/cows", 30)]
_hits = {}


def client_ip(request):
    """Cloud Run appends the real client address to the end of X-Forwarded-For, so the last entry cannot be forged."""
    fwd = request.headers.get("x-forwarded-for", "")
    return fwd.split(",")[-1].strip() if fwd else (request.client.host if request.client else "?")


@app.middleware("http")
async def guard(request, call_next):
    path = request.url.path
    if request.method in ("POST", "GET") and path.startswith("/api/") and not (ADMIN_KEY and request.headers.get("x-admin-key") == ADMIN_KEY):
        for key, cap in LIMITS:
            if (path.endswith(key) if key == "/report" else path.startswith(key)) and (key != "/api/cows" or request.method == "POST"):
                t, bucket = time.time(), _hits.setdefault((client_ip(request), key), [])
                bucket[:] = [x for x in bucket if t - x < 60]
                if len(bucket) >= cap:
                    return JSONResponse({"detail": "Too many requests. Please wait a minute and try again."}, status_code=429,
                                        headers={"Retry-After": "60"})
                bucket.append(t)
                if len(_hits) > 5000:
                    _hits.clear()
                break
    resp = await call_next(request)
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["Referrer-Policy"] = "no-referrer"
    return resp


# ------------------------------------------------------------------------------------------------ helpers
def now():
    return time.time()


def read_image(s: str) -> bytes:
    if not s:
        raise HTTPException(400, "image missing")
    raw = base64.b64decode(s.split(",", 1)[1] if s.startswith("data:") else s)
    if len(raw) > MAX_BYTES:
        raise HTTPException(413, "image too large")
    return raw


def data_url(jpeg: bytes) -> str:
    return "data:image/jpeg;base64," + base64.b64encode(jpeg).decode()


def need_admin(key):
    if not ADMIN_KEY or key != ADMIN_KEY:
        raise HTTPException(403, "admin key required")


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
        raise HTTPException(404, "cow not found")
    return dict(c, id=cid)


def all_cows():
    return [dict(c) for c in store.list("cows")]


# ------------------------------------------------------------------------------------------------ matching
def match_face(ident, cows):
    """Best registered cow for the sharpest face in an identify result -> (cow, score) or (None, best score)."""
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
    return (best, best_s) if best_s >= FACE_MATCH else (None, best_s)


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


# ------------------------------------------------------------------------------------------------ cows
class Register(BaseModel):
    name: str = ""
    tag: str
    breed: str = ""
    age: str = ""
    photos: dict[str, str]          # front / left / right / back as data URLs


@app.post("/api/cows")
def register(r: Register):
    tag = r.tag.strip()
    if not tag:
        raise HTTPException(400, "ear tag required")
    jpegs = {k: infer_mod.shrink_jpeg(read_image(v)) for k, v in r.photos.items() if v}
    keys = list(jpegs)
    preds = infer.predict([{"task": "identify", "image_b64": infer_mod.b64(jpegs[k])} for k in keys]) if keys else []
    embs, faces = [], {}
    for k, p in zip(keys, preds):
        f = rules.best_face(p)
        faces[k] = bool(f)
        if f:
            embs.append({"v": f["embedding"]})
    cid = re.sub(r"[^a-z0-9]+", "-", (r.name or "cow").lower()).strip("-") + "-" + tag
    first = jpegs.get("front") or (jpegs[keys[0]] if keys else None)
    doc = {"name": r.name.strip() or f"Cow {tag}", "tag": tag, "breed": r.breed, "age": r.age, "camera": "Camera 1",
           "alert": False, "kind": None, "history": [], "last_seen": now(), "embeddings": embs, "faces": faces,
           "tile": data_url(infer_mod.shrink_jpeg(first, 360, 80)) if first else None,
           "scene": data_url(infer_mod.shrink_jpeg(first, 720, 80)) if first else None, "created": now()}
    store.put("cows", cid, doc)
    return {"cow": public(dict(doc, id=cid)), "faces_found": sum(faces.values()),
            "warning": None if embs else "No cow face was found in the photos, so the cow can only be matched by ear tag."}


@app.get("/api/cows")
def cows():
    out = [public(c) for c in all_cows()]
    out.sort(key=lambda c: (not c["alert"], c["name"]))
    return out


@app.get("/api/cows/{cid}")
def cow(cid: str):
    return public(get_cow(cid))


# ------------------------------------------------------------------------------------------------ habit trends
TREND_QUERY = {"rest": "cow lying down more than usual and not eating what to do",
               "down": "cow lying down for hours will not get up what to do",
               "eating": "cow eating less loss of appetite what to do"}


def trend_message(kind, name, severity="medium"):
    passages = []
    try:
        passages = kb.search(TREND_QUERY[kind])
    except Exception:
        pass
    return messages.compose(kind, name, passages, severity, None)


def check_rest(cid):
    """Compare her resting share in the last 24 h with her own previous week; alert on a clear rise. -> trend dict."""
    c = get_cow(cid)
    tr = trends.rest_trend(store.list_where("posture_log", "cow_id", cid), now())
    if tr["flag"] and not c.get("alert"):
        msg, source = trend_message("rest", c["name"])
        store.update("cows", cid, {"alert": True, "kind": "rest", "severity": "medium", "short": messages.SHORT["rest"],
                                   "msg": msg, "source": source, "last_seen": now(), "box": None})
    return tr


def check_down(cid):
    """Has she been lying at every recent sighting for hours, without standing? High-severity alert, worded for 'go and look now'.
    Replaces a milder 'rest' alert but never a disease alert. -> the lying-streak dict."""
    c = get_cow(cid)
    st = suspects.lying_streak(store.list_where("posture_log", "cow_id", cid), now())
    if suspects.down_flag(st) and (not c.get("alert") or c.get("kind") == "rest"):
        msg, source = trend_message("down", c["name"], "high")
        if check_eating(c.get("camera") or "Camera 1")["flag"]:                  # sound agrees: say so
            for lang in messages.LANGS:
                msg[lang]["text"] = (msg[lang]["text"] + " " + suspects.ALSO_CHEWING[lang]).strip()
        store.update("cows", cid, {"alert": True, "kind": "down", "severity": "high", "short": messages.SHORT["down"],
                                   "msg": msg, "source": source, "last_seen": now(), "box": None})
    return st


def check_cow(cid):
    """All habit checks for one cow after a new sighting. -> the resting trend dict."""
    check_down(cid)
    return check_rest(cid)


def rank_suspects(camera):
    """Rank the cows of one camera group by how inactive or odd their recent sightings look. -> suspects.rank result."""
    t, scored = now(), []
    for c in all_cows():
        if (c.get("camera") or "Camera 1") != camera:
            continue
        entries = store.list_where("posture_log", "cow_id", c["id"])
        scored.append(suspects.score_cow(c, entries, trends.rest_trend(entries, t), trends.gait_trend(entries), t))
    return suspects.rank(scored)


def attach_suspects(alert, camera):
    """Add 'check this cow first' to a sound alert, in the three languages, and keep the ranking on the alert."""
    try:
        res = rank_suspects(camera)
    except Exception:
        logging.getLogger("gomitra").exception("suspect ranking failed")
        return alert
    line = suspects.lines(res)
    for lang in messages.LANGS:
        m = alert["msg"][lang]
        m["advice"] = (m.get("advice", "") + " " + line[lang]).strip()
    alert["check_first"] = line
    alert["suspects"] = [{"id": c["id"], "name": c["name"], "score": c["score"]} for c in res["ranked"][:3]]
    alert["stands_out"] = res["stands_out"]
    return alert


@app.get("/api/cows/{cid}/trends")
def cow_trends(cid: str):
    get_cow(cid)
    entries = store.list_where("posture_log", "cow_id", cid)
    return {"rest": trends.rest_trend(entries, now()), "gait": trends.gait_trend(entries),
            "streak": suspects.lying_streak(entries, now())}


@app.get("/api/cows/{cid}/report")
def vet_report(cid: str, lang: str = "en"):
    """Handover note for the vet: facts from stored data, written up by Gemini (plain text if Gemini is down)."""
    if lang not in messages.LANGS:
        raise HTTPException(400, "lang must be en, hi or te")
    trace.start()
    c = get_cow(cid)
    entries = store.list_where("posture_log", "cow_id", cid)
    facts = report.build_facts(c, store.list_where("observations", "cow_id", cid), trends.rest_trend(entries, now()),
                               trends.gait_trend(entries), check_eating(c.get("camera") or "Camera 1"), now())
    note, source = report.compose(facts, lang)
    return {"cow": c["name"], "lang": lang, "note": note, "source": source, "facts": facts, "time": now(),
            "trace": trace.get()}


_eat_cache = {}


def check_eating(camera):
    """Group chewing in the last 24 h against the previous week. One open alert per camera group. Cached for a minute."""
    hit = _eat_cache.get(camera)
    if hit and now() - hit[0] < 60:
        return hit[1]
    tr = trends.eat_trend(store.list_where("audio_events", "camera", camera), now())
    if tr["flag"]:
        open_ = [a for a in store.list_where("alerts", "kind", "eating")
                 if a.get("camera") == camera and not a.get("resolved") and now() - a["ts"] < 43200]
        if not open_:
            msg, source = trend_message("eating", camera)
            alert = {"kind": "eating", "camera": camera, "ts": now(), "severity": "medium",
                     "msg": msg, "source": source, "short": messages.SHORT["eating"], "resolved": False}
            store.put("alerts", uuid.uuid4().hex, attach_suspects(alert, camera))
    _eat_cache[camera] = (now(), tr)
    return tr


@app.post("/api/cows/{cid}/resolve")
def resolve(cid: str):
    get_cow(cid)
    store.update("cows", cid, {"alert": False, "kind": None, "severity": None, "short": None, "msg": None,
                               "box": None, "signals": {}, "history": []})
    return {"ok": True}


@app.delete("/api/cows/{cid}")
def remove(cid: str, x_admin_key: str = Header("")):
    need_admin(x_admin_key)
    store.delete("cows", cid)
    return {"ok": True}


# ------------------------------------------------------------------------------------------------ analyse a picture
class Analyze(BaseModel):
    image: str
    mode: str = "photo"             # "photo" = farmer upload (whole image), "cctv" = camera frame (find cows first)
    camera: str = "Camera 1"
    cow_id: str | None = None       # when the farmer already knows which cow it is
    read_tags: bool = False


def raise_alert(c, finding, scene_jpeg, box, camera):
    """Update a cow with a confirmed finding; the message is rewritten only when the finding changes."""
    kind = finding["kind"]
    upd = {"alert": True, "kind": kind, "severity": finding["severity"], "camera": camera, "box": box,
           "scene": data_url(scene_jpeg), "last_seen": now(), "short": messages.SHORT[kind],
           "signals": dict(c.get("signals") or {}, **{("walking" if kind == "limp" else "skin"): "check"})}
    if c.get("kind") != kind or not c.get("msg"):
        passages = []
        try:
            passages = kb.search({"lumpy": "lumpy skin disease what to do", "fmd": "foot and mouth disease what to do",
                                "limp": "lameness limping what to do"}[kind])
        except Exception:
            pass
        upd["msg"], upd["source"] = messages.compose(kind, c["name"], passages, finding["severity"], finding["p"])
    return upd


@app.post("/api/analyze")
def analyze(a: Analyze):
    trace.start()
    cctv = a.mode == "cctv"
    jpeg = infer_mod.shrink_jpeg(read_image(a.image))
    lumpy, ident = infer.vision(jpeg, cctv=cctv, read_tags=False)
    for p in (lumpy, ident):
        if p.get("error"):
            raise HTTPException(502, p["error"])
    registered = all_cows()
    scene = infer_mod.shrink_jpeg(jpeg, 720, 80)
    items = []                         # one per cow seen: (skin result dict, box, face-ident for matching)
    if cctv:
        H, W = cv2.imdecode(np.frombuffer(jpeg, np.uint8), cv2.IMREAD_COLOR).shape[:2]
        for c in lumpy["cows"]:
            x1, y1, x2, y2 = c["box"]          # sent to the app as fractions of the picture so any screen can draw it
            items.append({"usable": c["usable"], "reason": c.get("reason", ""), "probs": c.get("probs"),
                          "box": [round(x1 / W, 4), round(y1 / H, 4), round(x2 / W, 4), round(y2 / H, 4)],
                          "ident": face_in_box(ident, c["box"])})
    else:
        ph = lumpy["photo"]
        items.append({"usable": ph["usable"], "reason": ph.get("reason", ""), "probs": ph.get("probs"),
                      "box": None, "ident": ident, "cows_detected": ph.get("cows_detected")})
    results = []
    for it in items:
        cow_doc, score, method = None, 0.0, None
        if a.cow_id:
            cow_doc, method = get_cow(a.cow_id), "chosen"
        elif it["ident"]:
            cow_doc, score = match_face(it["ident"], registered)
            method = "face" if cow_doc else None
            if not cow_doc and (a.read_tags or ident.get("tags_in_frame")):
                ocr = infer.predict([{"task": "identify", "image_b64": infer_mod.b64(jpeg), "read_tags": True}])[0]
                cow_doc = match_tag(ocr, registered)
                method = "ear tag" if cow_doc else None
        finding = rules.skin_finding(it["probs"]) if it["usable"] else None
        res = {"usable": it["usable"], "reason": it["reason"], "probs": it["probs"], "box": it["box"],
               "finding": finding, "cow": None, "match": {"method": method, "score": round(score, 3)} if method else None,
               "alert": False, "message": None}
        if cow_doc:
            cid = cow_doc["id"]
            hist = list(cow_doc.get("history") or [])
            kind = finding["kind"] if finding else "ok"
            if it["usable"]:
                ok = bool(finding) and rules.confirmed(hist, kind, cctv)
                store.update("cows", cid, {"history": (hist + [kind])[-10:], "last_seen": now()})
                if ok:
                    upd = raise_alert(cow_doc, finding, scene, it["box"], a.camera)
                    store.update("cows", cid, upd)
                    res["alert"], res["message"] = True, upd.get("msg") or cow_doc.get("msg")
                elif not finding:
                    store.update("cows", cid, {"scene": data_url(scene), "last_seen": now(),
                                               "signals": dict(cow_doc.get("signals") or {}, skin="ok")})
                store.put("observations", uuid.uuid4().hex, {"cow_id": cid, "ts": now(), "kind": kind, "camera": a.camera,
                                                             "p": (finding or {}).get("p"), "mode": a.mode})
            res["cow"] = public(get_cow(cid))
        elif finding and it["usable"]:
            res["message"] = messages.template(finding["kind"], "this cow")      # not registered: say it, store nothing
        results.append(res)
    return {"mode": a.mode, "faces_in_frame": len(ident.get("faces", [])), "results": results, "trace": trace.get()}


# ------------------------------------------------------------------------------------------------ audio
class AudioIn(BaseModel):
    audio: str
    camera: str = "Camera 1"
    immediate: bool = False         # demo clips: alert from one clip instead of waiting for agreement


@app.post("/api/audio")
def audio(a: AudioIn):
    trace.start()
    res = infer.audio(read_image(a.audio))
    if res.get("error"):
        raise HTTPException(502, res["error"])
    ts = now()
    finding = rules.distress_finding(res)
    prior = sorted([e for e in store.list_where("audio_events", "camera", a.camera) if ts - e["ts"] < 1800],
                   key=lambda e: e["ts"])[-2:]
    store.put("audio_events", uuid.uuid4().hex, {
        "camera": a.camera, "ts": ts, "usable": res.get("usable"), "distress": bool(finding),
        "p_hfc": (res.get("distress") or {}).get("p_hfc"), "chew": (res.get("bite_chew") or {}).get("label")})
    alert = None
    if finding and (a.immediate or sum(1 for e in prior if e.get("distress")) >= 1):
        msg, source = messages.compose("distress", a.camera, [], "medium", finding["p"])
        alert = {"kind": "distress", "camera": a.camera, "ts": ts, "severity": "medium", "msg": msg, "source": source,
                 "short": messages.SHORT["distress"], "resolved": False}
        store.put("alerts", uuid.uuid4().hex, attach_suspects(alert, a.camera))
    return {"audio": res, "finding": finding, "alert": alert, "trace": trace.get(),
            "note": "One clip is not enough: distress alerts need two matching clips in 30 minutes."
            if finding and not alert else None}


class Posture(BaseModel):
    images: list[str]               # 1 to 5 pictures of the same cow (frames of a short walking clip, or a photo)
    cow_id: str | None = None
    camera: str = "Camera 1"


@app.post("/api/posture")
def posture(p: Posture):
    """Walking and resting check. Gait 3 or more raises a limp alert; the standing/lying label is saved on the cow."""
    if not p.images:
        raise HTTPException(400, "images missing")
    trace.start()
    jpegs = [infer_mod.shrink_jpeg(read_image(i), 960) for i in p.images[:5]]
    res = gait.analyze(jpegs)
    score = (res.get("gait") or {}).get("score")
    res["alert"], res["message"], res["cow"] = False, None, None
    if p.cow_id:
        c = get_cow(p.cow_id)
        sig = dict(c.get("signals") or {})
        if score is not None:
            sig["walking"] = "check" if score >= 3 else "watch" if score == 2 else "ok"
        if res.get("posture") and res["posture"].get("label") not in (None, "unknown"):
            sig["resting"] = res["posture"]["label"]
        store.update("cows", p.cow_id, {"signals": sig, "last_seen": now(), "gait_score": score})
        if score is not None and score >= 3:
            finding = {"kind": "limp", "p": round(score / 5, 2), "severity": "high" if score >= 4 else "medium"}
            scene = jpegs[0]
            upd = raise_alert(dict(c, signals=sig), finding, scene, None, p.camera)
            if res.get("overlay"):
                upd["scene"] = res["overlay"]
            store.update("cows", p.cow_id, upd)
            res["alert"], res["message"] = True, upd.get("msg") or c.get("msg")
        label = (res.get("posture") or {}).get("label")
        if label in ("standing", "sitting", "lying") or score is not None:       # keep a sighting for the habit trends
            entry = {"cow_id": p.cow_id, "ts": now(), "label": label if label in ("standing", "sitting", "lying") else None,
                     "gait": score}
            store.put("posture_log", uuid.uuid4().hex, entry)
            res["trend"] = {"rest": check_cow(p.cow_id),
                            "gait": trends.gait_trend(store.list_where("posture_log", "cow_id", p.cow_id))}
        res["cow"] = public(get_cow(p.cow_id))
    elif score is not None and score >= 3:
        res["message"] = messages.template("limp", "this cow")
    res["trace"] = trace.get()
    return res


# ------------------------------------------------------------------------------------------------ device ingest (Raspberry Pi)
DEVICE_KEY = os.getenv("DEVICE_KEY", "")
POSTURE_EVERY = 600                  # seconds between walking/resting checks for the same cow (the pose model is the slow one)
_last_pose = {}
_ring = {"n": random.randrange(50)}     # next slot of the 50-document event log (random start so several instances do not all begin at 0)


class Ingest(BaseModel):
    file: str                        # base64 of one photo, one sound clip or one short video
    camera: str = "Camera 1"


def sniff(raw):
    """What a file is, from its first bytes (a Pi does not need to say)."""
    if raw[:3] == b"\xff\xd8\xff" or raw[:8] == b"\x89PNG\r\n\x1a\n":
        return "image"
    if raw[:4] == b"RIFF" and raw[8:12] == b"WAVE":
        return "audio"
    if raw[4:8] == b"ftyp" or raw[:4] == b"\x1aE\xdf\xa3":
        return "video"
    return None


def video_frames(raw, per_s=3.0, max_n=24):
    """About per_s frames a second from a short video, at most max_n, spread over the whole clip. -> [(time_s, JPEG up to 1024 px)]"""
    import tempfile
    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
        f.write(raw)
        path = f.name
    try:
        cap = cv2.VideoCapture(path)
        fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 0
        step = max(1, int(round(fps / per_s)))
        idx = list(range(0, total, step))
        if len(idx) > max_n:
            idx = [idx[int(i * (len(idx) - 1) / (max_n - 1))] for i in range(max_n)]
        out = []
        for i in idx:
            cap.set(cv2.CAP_PROP_POS_FRAMES, i)
            ok, fr = cap.read()
            if ok:
                out.append((i / fps, infer_mod.shrink_jpeg(cv2.imencode(".jpg", fr, [cv2.IMWRITE_JPEG_QUALITY, 90])[1].tobytes())))
        cap.release()
        return out
    finally:
        os.unlink(path)


def detect_frames(kept):
    """Run the cow detector (skin model's detector) and the cow-face finder on the screened frames, four frames per call,
    then let the agent assess each one."""
    for i in range(0, len(kept), 4):
        chunk, insts = kept[i:i + 4], []
        for k in chunk:
            small = base64.b64encode(cv2.imencode(".jpg", k["img"], [cv2.IMWRITE_JPEG_QUALITY, 80])[1].tobytes()).decode()
            insts += [{"task": "lumpy", "image_b64": small}, {"task": "identify", "image_b64": small, "read_tags": False}]
        preds = infer.predict(insts)
        for j, k in enumerate(chunk):
            for p in (preds[2 * j], preds[2 * j + 1]):
                if p.get("error"):
                    raise HTTPException(502, p["error"])
            agent.assess(k, preds[2 * j].get("cows", []), preds[2 * j + 1].get("faces", []))


def log_ingest(camera, kind, steps, summary, decisions=()):
    """Last 50 device events in a ring of documents (so the table never grows)."""
    t = now()
    _ring["n"] = (_ring["n"] + 1) % 50
    store.put("ingest_log", f"r{_ring['n']}", {"ts": t, "camera": camera, "kind": kind, "steps": steps, "summary": summary,
                                              "decisions": list(decisions)})


@app.post("/api/ingest")
def ingest(b: Ingest, x_device_key: str = Header("")):
    """One address for the Pi. Looks at what arrived and sends it to the right model:
    photo or video -> the frame agent (router/agent.py) keeps the good frames and routes them: clear face -> cow-face model,
    clearly visible cow -> skin model and alert rules, side-on fully visible cow -> pose model and walking check
    (at most every 10 minutes per cow); frames that fail every check reach no model.
    sound clip -> distress and eating-sound models."""
    if not DEVICE_KEY or x_device_key != DEVICE_KEY:
        raise HTTPException(403, "device key required")
    raw = read_image(b.file)
    kind = sniff(raw)
    if kind is None:
        raise HTTPException(415, "send a JPEG/PNG photo, a WAV sound clip or an MP4 video")
    steps, out = [f"detected {kind}"], {}
    if kind == "audio":
        r = audio(AudioIn(audio=b.file, camera=b.camera))
        steps.append("sound models")
        eat = (r["audio"].get("bite_chew") or {}).get("label")
        summary = (f"Sound clip: {'loud distress-like call' if r['finding'] else 'no distress call'}"
                   f"{', eating sound: ' + eat if eat else ''}{'; alert raised' if r['alert'] else ''}.")
        out = {"alert": bool(r["alert"]), "distress": bool(r["finding"])}
    else:
        frames = [(0.0, raw)]
        if kind == "video":
            frames = video_frames(raw)
            if not frames:
                raise HTTPException(422, "no frames could be read from the video")
        label = "Video" if kind == "video" else "Photo"
        # 1. frame agent: keep the good frames and decide which model each goes to
        kept, dropped = agent.screen(frames)
        decisions = [f"Looked at {len(frames)} frame(s); {len(kept)} passed the sharpness, brightness and duplicate checks"
                     + (f" (dropped: {', '.join(f'{v} {k}' for k, v in dropped.items())})." if dropped else ".")]
        steps.append(f"frame agent: {len(frames)} frame(s) -> {len(kept)} screened")
        plan = None
        if kept:
            detect_frames(kept)
            steps.append("cow detector and face finder on the screened frames")
            plan = agent.choose(kept)
            decisions += plan["decisions"] + ["Not used, " + d for d in plan["drops"][:5]]
        if not plan or not (plan["skin"] or plan["face"] or plan["gait"]):
            why = (plan["drops"][0] if plan and plan["drops"] else "no frame was clear enough")
            summary = f"{label}: no usable frame ({why}). Nothing was sent to the models."
            decisions.append("Nothing was sent to the skin, face or pose models.")
            log_ingest(b.camera, kind, steps, summary, decisions)
            return {"kind": kind, "camera": b.camera, "steps": steps, "summary": summary, "decisions": decisions, "routed": False}
        # 2. who is it? the clearest face frame goes to the cow-face model (only trusted when one cow is in view)
        analyze_frame = plan["skin"] or plan["face"] or plan["gait"][0]
        cow_id = None
        if plan["face"] and plan["face"]["cows_seen"] <= 1 and analyze_frame["cows_seen"] <= 1:
            ident = infer.identify(plan["face"]["jpeg"])
            steps.append("cow-face model on the best face frame")
            cow_doc, _ = match_face(ident, all_cows())
            cow_id = cow_doc["id"] if cow_doc else None
        # 3. skin screening and alert rules on the best skin frame
        a = analyze(Analyze(image=base64.b64encode(analyze_frame["jpeg"]).decode(), mode="cctv", camera=b.camera, cow_id=cow_id))
        steps += ["skin model", "alert rules"]
        known = [x for x in a["results"] if x["cow"]]
        parts = [f"{len(a['results'])} cow(s) in the chosen frame" if a["results"] else "no cow found in the chosen frame"]
        for x in known:
            parts.append(f"{x['cow']['name']}: " + (x["finding"]["kind"] if x["finding"] else "skin normal") + (", alert raised" if x["alert"] else ""))
        if a["results"] and not known:
            parts.append("not matched to a registered cow")
        out = {"cows": [x["cow"]["name"] for x in known], "alert": any(x["alert"] for x in known)}
        # 4. walking and resting: only the side-on frames, only for one recognised cow, and not more than every 10 minutes
        if len(known) == 1 and plan["gait"] and now() - _last_pose.get(known[0]["cow"]["id"], 0) > POSTURE_EVERY:
            cid = known[0]["cow"]["id"]
            _last_pose[cid] = now()
            try:
                p = posture(Posture(images=[base64.b64encode(g["jpeg"]).decode() for g in plan["gait"]], cow_id=cid, camera=b.camera))
                steps += ["pose model", "gait score"]
                lab = (p.get("posture") or {}).get("label")
                sc = (p.get("gait") or {}).get("score")
                parts.append(f"walking/resting check on {len(plan['gait'])} side-on frame(s): {lab or 'posture unknown'}" + (f", gait score {sc}" if sc else ""))
                out["posture"] = lab
            except Exception as e:
                _last_pose[cid] = 0.0
                parts.append(f"walking/resting check failed ({type(e).__name__})")
        summary = f"{label}: " + "; ".join(parts) + "."
        out["decisions"], out["routed"] = decisions, True
    log_ingest(b.camera, kind, steps, summary, out.get("decisions", []))
    return {"kind": kind, "camera": b.camera, "steps": steps, "summary": summary, **out}


@app.get("/api/ingest/recent")
def ingest_recent():
    """What the devices sent lately and where it was routed (no pictures)."""
    return sorted(store.list("ingest_log"), key=lambda e: -e["ts"])[:10]


_warm = {"at": 0.0}


@app.post("/api/warmup")
def warmup():
    """The app calls this when it opens, so the pose service (which sleeps when idle) is already awake by the time someone
    runs a walking check. Runs one small check and waits for it, so the request keeps this service's CPU on. Skips if
    a warm-up ran in the last 4 minutes."""
    refreshed = False
    try:
        refreshed = ensure_history()
    except Exception:
        logging.getLogger("gomitra").exception("demo history refresh failed")
    extra = {"demo_refreshed": True} if refreshed else {}
    if not gait.POSE_URL or now() - _warm["at"] < 240:
        return {"started": False, **extra}
    _warm["at"] = now()
    try:
        with open(os.path.join(HERE, "static", "samples", "walk_lame.jpg"), "rb") as f:
            gait.call_pose([f.read()])
        return {"started": True, "ok": True, **extra}
    except Exception as e:
        _warm["at"] = 0.0
        return {"started": True, "ok": False, "error": type(e).__name__, **extra}


@app.get("/api/sounds")
def sounds(camera: str = "North field camera"):
    """What the microphone group heard today: chewing time and meals, and the latest distress call."""
    f = feeding(camera)
    ev = [e for e in store.list_where("audio_events", "camera", camera) if e.get("distress")]
    last = max((e["ts"] for e in ev), default=None)
    tr = check_eating(camera)
    open_ = [a for k in ("distress", "eating") for a in store.list_where("alerts", "kind", k)
             if a.get("camera") == camera and not a.get("resolved") and a.get("check_first") and now() - a["ts"] < 43200]
    latest = max(open_, key=lambda a: a["ts"], default=None)
    return dict(f, last_distress=last, distress_clips=len(ev), trend=tr,
                check_first=(latest or {}).get("check_first"), check_first_stands_out=(latest or {}).get("stands_out"))


@app.get("/api/alerts")
def alerts():
    out = [a for a in store.list("alerts") if not a.get("resolved")]
    return sorted(out, key=lambda a: -a["ts"])[:20]


@app.post("/api/alerts/{aid}/resolve")
def resolve_alert(aid: str):
    store.update("alerts", aid, {"resolved": True})
    return {"ok": True}


@app.get("/api/feeding")
def feeding(camera: str = "Camera 1"):
    """Today's chewing activity for a camera group, from the bite/chew clips. Meals split at 5-minute gaps."""
    t = now()
    ev = [e for e in store.list_where("audio_events", "camera", camera) if e.get("chew") and t - 86400 <= e["ts"] < t]
    minutes, meals = trends.chew_minutes(ev, t - 86400, t)
    return {"camera": camera, "clips": len(ev), "meals": meals, "minutes": minutes}


# ------------------------------------------------------------------------------------------------ knowledge + assistant
class Ask(BaseModel):
    question: str
    lang: str = "en"
    cow_id: str | None = None


@app.post("/api/ask")
def ask(q: Ask):
    if q.lang not in messages.LANGS:
        raise HTTPException(400, "lang must be en, hi or te")
    name = None
    if q.cow_id:
        c = store.get("cows", q.cow_id) or {}
        name = c.get("name")
    try:
        trace.start()
        out = kb.answer(q.question.strip(), q.lang, name)
        out["trace"] = trace.get()
        return out
    except Exception as e:
        raise HTTPException(502, f"assistant unavailable: {type(e).__name__}")


class KbDoc(BaseModel):
    source: str
    text: str | None = None
    pdf: str | None = None          # base64 of a PDF


@app.post("/api/admin/kb")
def kb_add(d: KbDoc, x_admin_key: str = Header("")):
    need_admin(x_admin_key)
    text = d.text or kb_mod_pdf(base64.b64decode(d.pdf or ""))
    return {"source": d.source, "chunks": kb.add(d.source, text)}


@app.delete("/api/admin/kb/{source}")
def kb_remove(source: str, x_admin_key: str = Header("")):
    need_admin(x_admin_key)
    return {"removed": kb.remove(source)}


def kb_mod_pdf(data):
    from kb import pdf_text
    return pdf_text(data)


@app.get("/api/kb")
def kb_sources():
    return kb.sources()


# ------------------------------------------------------------------------------------------------ demo + status
DEMO_COWS = [("gauri", "Gauri", "0417", "Holstein-Friesian", "5 years"), ("nandini", "Nandini", "0388", "Holstein-Friesian cross", "6 years"),
             ("rani", "Rani", "0451", "Holstein-Friesian cross", "4 years"), ("kamala", "Kamala", "0452", "Holstein-Friesian", "6 years"),
             ("lakshmi", "Lakshmi", "0412", "Holstein-Friesian", "4 years"), ("radha", "Radha", "0405", "Holstein-Friesian cross", "6 years"),
             ("ganga", "Ganga", "0431", "Holstein-Friesian cross", "3 years"), ("yamuna", "Yamuna", "0426", "Holstein-Friesian", "5 years"),
             ("tulasi", "Tulasi", "0439", "Holstein-Friesian cross", "4 years"), ("saraswati", "Saraswati", "0398", "Holstein-Friesian", "7 years"),
             ("kavya", "Kavya", "0444", "Holstein-Friesian cross", "2 years"), ("sita", "Sita", "0409", "Holstein-Friesian cross", "5 years")]


@app.post("/api/demo/seed")
def seed(x_admin_key: str = Header("")):
    need_admin(x_admin_key)
    n = 0
    for cid, name, tag, breed, age in DEMO_COWS:
        if not store.get("cows", cid):
            store.put("cows", cid, {"name": name, "tag": tag, "breed": breed, "age": age, "camera": "North field camera",
                                    "alert": False, "history": [], "last_seen": now(), "embeddings": [], "demo": True,
                                    "created": now()})
            n += 1
    return {"added": n}


HISTORY_CAMERA = "North field camera"
# resting sightings out of 12 per day: (usual day, last 24 h). Tulasi rests far more than her usual; the others do not.
HISTORY_REST = {"tulasi": (5, 9), "kamala": (5, 5), "lakshmi": (5, 6), "nandini": (5, 5)}
HISTORY_GAIT = {"nandini": [1, 1, 1, 2, 2]}        # oldest first, one score per day over the last 5 days


HISTORY_REFRESH = 90 * 60        # the simulated week is rebuilt when it is older than this (the windows roll with the clock, and
                                 # "down for hours" needs a sighting from the last 3 hours)
_hist_check = {"at": 0.0}


@app.post("/api/demo/history")
def seed_history(x_admin_key: str = Header("")):
    need_admin(x_admin_key)
    return build_history()


def ensure_history():
    """Called when the app opens: rebuild the simulated week if it is missing or old, so the demo cows always match the
    test guide, whenever the jury looks. Turn off with AUTO_DEMO=0. -> True if it rebuilt."""
    if os.getenv("AUTO_DEMO", "1") != "1" or now() - _hist_check["at"] < 120:
        return False
    _hist_check["at"] = now()
    m = store.get("meta", "demo_history")
    if (m and now() - m["ts"] < HISTORY_REFRESH) or not store.get("cows", "tulasi"):
        return False
    store.put("meta", "demo_history", {"ts": now()})          # claim it first, so two visitors do not both rebuild
    build_history()
    return True


@app.post("/api/demo/reset")
def reset_demo(keep_cows: bool = False, x_admin_key: str = Header("")):
    """Back to a clean demo: removes all alerts, observations, sound events, sightings and device logs, clears every cow's
    alert and history, deletes cows that are not demo cows (unless keep_cows), then reloads the demo cows and the simulated
    week. The vet documents are not touched."""
    need_admin(x_admin_key)
    for col in ("observations", "alerts", "audio_events", "posture_log", "ingest_log", "meta"):
        store.delete_many(col, [d["id"] for d in store.list(col)])
    removed = 0
    for c in all_cows():
        if c.get("demo"):
            store.update("cows", c["id"], {"alert": False, "kind": None, "severity": None, "short": None, "msg": None,
                                           "source": None, "box": None, "signals": {}, "history": [], "scene": None,
                                           "gait_score": None, "camera": HISTORY_CAMERA, "last_seen": now()})
        elif not keep_cows:
            store.delete("cows", c["id"])
            removed += 1
    added = seed(x_admin_key)["added"]
    _eat_cache.clear()
    _last_pose.clear()
    return {"cows_removed": removed, "demo_cows_added": added, "history": build_history()}


def build_history():
    """SIMULATED week of habit data so the trend alerts can be shown. Safe to repeat: it replaces its own earlier data.
    The windows are the 24 h blocks before 'now', so the data is rebuilt as it ages (see ensure_history)."""
    t0, rng = now(), random.Random(7)
    for col in ("posture_log", "audio_events"):
        store.delete_many(col, [d["id"] for d in store.list_where(col, "demo", True)])
    for a in store.list_where("alerts", "kind", "eating"):
        if a.get("camera") == HISTORY_CAMERA:
            store.update("alerts", a["id"], {"resolved": True})
    posture = []
    for cid, (usual, today) in HISTORY_REST.items():
        c = store.get("cows", cid)
        if not c:
            continue
        if c.get("kind") in ("rest", "down"):
            store.update("cows", cid, {"alert": False, "kind": None, "short": None, "msg": None, "severity": None})
        for k in range(trends.WINDOWS):
            n_rest = today if k == 0 else usual + rng.choice((-1, 0, 0, 1))
            labels = [("sitting" if i % 4 == 3 else "lying") for i in range(n_rest)] + ["standing"] * (12 - n_rest)
            rng.shuffle(labels)
            if k == 0:       # newest sighting first: Tulasi has been down for hours; everyone else was seen standing most recently
                if cid == "tulasi":
                    labels = ["lying"] * 4 + [l for l in labels if l == "standing"] + ["lying"] * (n_rest - 4)
                    rest = labels[4:]; rng.shuffle(rest); labels = labels[:4] + rest
                elif "standing" in labels:
                    j = labels.index("standing"); labels[0], labels[j] = labels[j], labels[0]
            for i, lab in enumerate(labels):
                e = {"cow_id": cid, "ts": t0 - k * trends.DAY - (i + 0.5) * 7200, "label": lab, "gait": None, "demo": True}
                if i == 0 and cid in HISTORY_GAIT and k < len(HISTORY_GAIT[cid]):
                    e["gait"] = HISTORY_GAIT[cid][len(HISTORY_GAIT[cid]) - 1 - k]
                posture.append((uuid.uuid4().hex, e))
    store.put_many("posture_log", posture)
    chew = []
    for k in range(trends.WINDOWS):
        starts = (6, 17) if k == 0 else (2, 8, 14, 20)           # hours into the day; the last 24 h has only two meals
        for h in starts:
            for j in range(rng.choice((11, 12, 13))):
                ts = t0 - (k + 1) * trends.DAY + h * 3600 + j * 120
                chew.append((uuid.uuid4().hex, {"camera": HISTORY_CAMERA, "ts": ts, "usable": True, "distress": False,
                                                "p_hfc": 0.0, "chew": "chewing", "demo": True}))
    store.put_many("audio_events", chew)
    _eat_cache.clear()
    out = {"posture_sightings": len(posture), "chew_clips": len(chew), "cows": {}}
    for cid in HISTORY_REST:
        if store.get("cows", cid):
            tr = check_cow(cid)
            out["cows"][cid] = {k: tr[k] for k in ("today", "base", "flag")}
    out["eating"] = check_eating(HISTORY_CAMERA)
    store.put("meta", "demo_history", {"ts": now()})
    return out


@app.get("/api/status")
def status():
    return {"infer_backend": infer_mod.BACKEND, "project": infer_mod.PROJECT, "region": infer_mod.REGION,
            "endpoint_id": infer_mod.ENDPOINT_ID or None, "gemini_model": messages.GEMINI_MODEL,
            "cows": len(store.list("cows")), "kb_sources": kb.sources(), "time": now()}


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/")
def index():
    return FileResponse(os.path.join(HERE, "static", "index.html"))


app.mount("/static", StaticFiles(directory=os.path.join(HERE, "static")), name="static")
