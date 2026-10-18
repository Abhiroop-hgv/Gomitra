"""The Raspberry Pi entry point: one upload address for photos, short videos and sound clips.

The router looks at what arrived and routes it with fixed rules (no model guesses where a file goes):
  photo or video -> the frame agent (domain/agent.py) keeps the good frames and routes them: a clear face -> cow-face model,
                    a clearly visible cow -> skin model and alert rules, a side-on fully visible cow -> pose model and walking
                    check (at most every 10 minutes per cow). Frames that fail every check reach no model.
  sound clip     -> distress and eating-sound models.
"""
import base64
import os
import random
import tempfile

import cv2

from gomitra import config
from gomitra.context import infer, store
from gomitra.core.util import now, read_image
from gomitra.domain import agent, matching
from gomitra.errors import Unprocessable, UnsupportedMedia, UpstreamError
from gomitra.infra import inference as inf
from gomitra.services import analysis, posture
from gomitra.services.audio import process_audio
from gomitra.services.cows import all_cows

_last_pose = {}
_ring = {"n": random.randrange(50)}     # next slot of the 50-document event log (random start so several instances do not all begin at 0)


def clear_state():
    _last_pose.clear()


def sniff(raw):
    """What a file is, from its first bytes (a Pi does not need to say): "image", "audio", "video" or None."""
    if raw[:3] == b"\xff\xd8\xff" or raw[:8] == b"\x89PNG\r\n\x1a\n":
        return "image"
    if raw[:4] == b"RIFF" and raw[8:12] == b"WAVE":
        return "audio"
    if raw[4:8] == b"ftyp" or raw[:4] == b"\x1aE\xdf\xa3":
        return "video"
    return None


def video_frames(raw, per_s=3.0, max_n=24):
    """About per_s frames a second from a short video, at most max_n, spread over the whole clip. -> [(time_s, JPEG up to 1024 px)]"""
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
                out.append((i / fps, inf.shrink_jpeg(cv2.imencode(".jpg", fr, [cv2.IMWRITE_JPEG_QUALITY, 90])[1].tobytes())))
        cap.release()
        return out
    finally:
        os.unlink(path)


def detect_frames(kept):
    """Run the cow detector (the skin model's detector) and the cow-face finder on the screened frames, four frames per call,
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
                    raise UpstreamError(p["error"])
            agent.assess(k, preds[2 * j].get("cows", []), preds[2 * j + 1].get("faces", []))


def log_ingest(camera, kind, steps, summary, decisions=()):
    """Last 50 device events in a ring of documents (so the table never grows)."""
    _ring["n"] = (_ring["n"] + 1) % 50
    store.put("ingest_log", f"r{_ring['n']}", {"ts": now(), "camera": camera, "kind": kind, "steps": steps, "summary": summary,
                                              "decisions": list(decisions)})


def recent():
    """What the devices sent lately and where it was routed (no pictures)."""
    return sorted(store.list("ingest_log"), key=lambda e: -e["ts"])[:10]


def handle(file, camera="Camera 1"):
    raw = read_image(file)
    kind = sniff(raw)
    if kind is None:
        raise UnsupportedMedia("send a JPEG/PNG photo, a WAV sound clip or an MP4 video")
    steps = [f"detected {kind}"]
    if kind == "audio":
        return _handle_audio(file, camera, kind, steps)
    return _handle_frames(raw, camera, kind, steps)


def _handle_audio(file, camera, kind, steps):
    r = process_audio(file, camera)
    steps.append("sound models")
    eat = (r["audio"].get("bite_chew") or {}).get("label")
    summary = (f"Sound clip: {'loud distress-like call' if r['finding'] else 'no distress call'}"
               f"{', eating sound: ' + eat if eat else ''}{'; alert raised' if r['alert'] else ''}.")
    log_ingest(camera, kind, steps, summary)
    return {"kind": kind, "camera": camera, "steps": steps, "summary": summary,
            "alert": bool(r["alert"]), "distress": bool(r["finding"])}


def _handle_frames(raw, camera, kind, steps):
    frames = [(0.0, raw)]
    if kind == "video":
        frames = video_frames(raw)
        if not frames:
            raise Unprocessable("no frames could be read from the video")
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
        why = plan["drops"][0] if plan and plan["drops"] else "no frame was clear enough"
        summary = f"{label}: no usable frame ({why}). Nothing was sent to the models."
        decisions.append("Nothing was sent to the skin, face or pose models.")
        log_ingest(camera, kind, steps, summary, decisions)
        return {"kind": kind, "camera": camera, "steps": steps, "summary": summary, "decisions": decisions, "routed": False}
    # 2. who is it? the clearest face frame goes to the cow-face model (only trusted when one cow is in view)
    analyze_frame = plan["skin"] or plan["face"] or plan["gait"][0]
    cow_id = None
    if plan["face"] and plan["face"]["cows_seen"] <= 1 and analyze_frame["cows_seen"] <= 1:
        ident = infer.identify(plan["face"]["jpeg"])
        steps.append("cow-face model on the best face frame")
        cow_doc, _ = matching.match_face(ident, all_cows())
        cow_id = cow_doc["id"] if cow_doc else None
    # 3. skin screening and alert rules on the best skin frame
    a = analysis.analyze(base64.b64encode(analyze_frame["jpeg"]).decode(), mode="cctv", camera=camera, cow_id=cow_id)
    steps += ["skin model", "alert rules"]
    known = [x for x in a["results"] if x["cow"]]
    parts = [f"{len(a['results'])} cow(s) in the chosen frame" if a["results"] else "no cow found in the chosen frame"]
    for x in known:
        parts.append(f"{x['cow']['name']}: " + (x["finding"]["kind"] if x["finding"] else "skin normal") + (", alert raised" if x["alert"] else ""))
    if a["results"] and not known:
        parts.append("not matched to a registered cow")
    out = {"cows": [x["cow"]["name"] for x in known], "alert": any(x["alert"] for x in known)}
    # 4. walking and resting: only the side-on frames, only for one recognised cow, and not more than every 10 minutes
    if len(known) == 1 and plan["gait"] and now() - _last_pose.get(known[0]["cow"]["id"], 0) > config.POSTURE_EVERY:
        cid = known[0]["cow"]["id"]
        _last_pose[cid] = now()
        try:
            p = posture.check_posture([base64.b64encode(g["jpeg"]).decode() for g in plan["gait"]], cow_id=cid, camera=camera)
            steps += ["pose model", "gait score"]
            lab = (p.get("posture") or {}).get("label")
            sc = (p.get("gait") or {}).get("score")
            parts.append(f"walking/resting check on {len(plan['gait'])} side-on frame(s): {lab or 'posture unknown'}" + (f", gait score {sc}" if sc else ""))
            out["posture"] = lab
        except Exception as e:
            _last_pose[cid] = 0.0
            parts.append(f"walking/resting check failed ({type(e).__name__})")
    summary = f"{label}: " + "; ".join(parts) + "."
    log_ingest(camera, kind, steps, summary, decisions)
    return {"kind": kind, "camera": camera, "steps": steps, "summary": summary, "decisions": decisions, "routed": True, **out}
