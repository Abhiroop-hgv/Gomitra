"""Frame agent: from the frames a camera sends, keep the good ones and decide which model each one goes to.

Rules, not a language model: cheap OpenCV checks first, then the cow detector and cow-face model look at the few frames that
survive, then each frame is routed:
  face frame (a cow face is clear)            -> cow-face model: who is this cow?
  skin frame (cow clearly visible, not tiny)  -> skin screening model (lumpy skin / foot-and-mouth signs)
  gait frames (cow side-on, fully visible,    -> pose model + Gemini walking/resting check
               not blocked, big enough)
Frames that fail every check are dropped and never reach a model, which saves cost and avoids false alerts.

The checks and the ranking weights are ported from the team's frame_extraction.py (pick the best frame of a cow from a video):
cut-off, occlusion and too-small gates, then a score from side-on-ness, sharpness, size and detector confidence.
This module is pure logic (no network), so it can be tested without any model.
"""
import cv2
import numpy as np

SMALL_SIDE = 640            # frames are looked at in this size for screening and detection
MAX_CANDIDATES = 8          # at most this many frames go to the detector
MIN_BRIGHT, MAX_BRIGHT = 35, 235
MIN_SHARP = 60.0            # Laplacian variance of the whole small frame; below this the frame is treated as blurred
DUP_DIFF = 3.0              # mean grey difference (0-255) below this to the last kept frame = near duplicate
EDGE_MARGIN = 0.02          # the cow's box must stay this fraction of the frame away from every edge (gait frames)
MAX_OVERLAP = 0.15          # another cow may cover at most this fraction of the target (gait frames)
GAIT_MIN_AREA = 0.10        # the cow must fill this much of the frame to read the legs (gait frames)
SKIN_MIN_AREA = 0.04        # and this much for the skin model
COW_CONF = 0.5
SIDE_ASPECT = (1.3, 2.4)    # width / height of a standing cow seen from the side
SIDE_OK = 0.6               # side-on score needed for a gait frame
WEIGHTS = (0.35, 0.25, 0.25, 0.15)      # side-on, sharpness, size, detector confidence
GAIT_FRAMES, GAIT_GAP_S = 5, 0.5


def small_gray(jpeg):
    """-> (small BGR image, grey image) or (None, None) if the bytes are not an image."""
    img = cv2.imdecode(np.frombuffer(jpeg, np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        return None, None
    h, w = img.shape[:2]
    s = min(1.0, SMALL_SIDE / max(h, w))
    if s < 1:
        img = cv2.resize(img, (round(w * s), round(h * s)), interpolation=cv2.INTER_AREA)
    return img, cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)


def screen(frames, max_candidates=MAX_CANDIDATES):
    """frames: [(time_s, jpeg bytes)]. Cheap checks on the router: drop undecodable, too dark or bright, blurred and
    near-duplicate frames, then keep the sharpest few. -> (kept list of dicts in time order, dropped counts by reason)."""
    dropped = {"unreadable": 0, "too dark/bright": 0, "blurred": 0, "near-duplicate": 0, "not among the sharpest": 0}
    kept, last = [], None
    for idx, (t, jpeg) in enumerate(frames):
        img, gray = small_gray(jpeg)
        if img is None:
            dropped["unreadable"] += 1
            continue
        bright = float(gray.mean())
        sharp = float(cv2.Laplacian(gray, cv2.CV_64F).var())
        if not MIN_BRIGHT <= bright <= MAX_BRIGHT:
            dropped["too dark/bright"] += 1
            continue
        if sharp < MIN_SHARP:
            dropped["blurred"] += 1
            continue
        tiny = cv2.resize(gray, (32, 32), interpolation=cv2.INTER_AREA).astype(np.float32)
        if last is not None and float(np.abs(tiny - last).mean()) < DUP_DIFF:
            dropped["near-duplicate"] += 1
            continue
        last = tiny
        kept.append({"idx": idx, "t": float(t), "jpeg": jpeg, "img": img, "sharp_frame": sharp,
                     "w": img.shape[1], "h": img.shape[0]})
    if len(kept) > max_candidates:
        keep_ids = {k["idx"] for k in sorted(kept, key=lambda k: -k["sharp_frame"])[:max_candidates]}
        dropped["not among the sharpest"] = len(kept) - max_candidates
        kept = [k for k in kept if k["idx"] in keep_ids]
    return kept, {k: v for k, v in dropped.items() if v}


def _area(b):
    return max(b[2] - b[0], 0) * max(b[3] - b[1], 0)


def _overlap(target, other):
    iw = min(target[2], other[2]) - max(target[0], other[0])
    ih = min(target[3], other[3]) - max(target[1], other[1])
    return 0.0 if iw <= 0 or ih <= 0 or _area(target) == 0 else iw * ih / _area(target)


def _side_score(box):
    w, h = box[2] - box[0], box[3] - box[1]
    if h <= 0:
        return 0.0
    aspect = w / h
    lo, hi = SIDE_ASPECT
    if lo <= aspect <= hi:
        return 1.0
    edge = lo if aspect < lo else hi
    return max(0.0, 1.0 - abs(aspect - edge) / edge)


def assess(info, cows, faces):
    """Fill in what the detector and the face model found in one screened frame.
    cows: the "cows" list of the skin model (box in pixels of the small frame, cow_conf, usable, reason);
    faces: the "faces" list of the cow-face model (box, conf, usable). Adds keys to info and returns it."""
    W, H = info["w"], info["h"]
    info["cows_seen"] = len([c for c in cows if c["cow_conf"] >= COW_CONF])
    good_faces = [f for f in faces if f.get("usable")]
    info["face"] = max(good_faces, key=lambda f: f["conf"]) if good_faces else None
    info.update(skin_ok=False, gait_ok=False, side=0.0, score=0.0, view="no cow", why="no cow found")
    sure = [c for c in cows if c["cow_conf"] >= COW_CONF]
    if not sure:
        if info["face"]:
            info.update(view="face", why="")
        return info
    target = max(sure, key=lambda c: _area(c["box"]))
    box = target["box"]
    area = _area(box) / (W * H)
    cut = box[0] < EDGE_MARGIN * W or box[1] < EDGE_MARGIN * H or box[2] > W - EDGE_MARGIN * W or box[3] > H - EDGE_MARGIN * H
    blocked = any(_overlap(box, o["box"]) > MAX_OVERLAP for o in sure if o is not target)
    info["side"] = _side_score(box)
    crop = info["img"][max(box[1], 0):box[3], max(box[0], 0):box[2]]
    info["sharp_box"] = float(cv2.Laplacian(cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY), cv2.CV_64F).var()) if crop.size else 0.0
    info["size"] = min(1.0, area / 0.4)
    info["conf"] = target["cow_conf"]
    info["skin_ok"] = bool(target.get("usable")) and area >= SKIN_MIN_AREA
    info["gait_ok"] = not cut and not blocked and area >= GAIT_MIN_AREA and info["side"] >= SIDE_OK
    info["view"] = "side-on" if info["side"] >= SIDE_OK else "front/rear/angled"
    reasons = []
    if cut:
        reasons.append("cow cut off by the edge")
    if blocked:
        reasons.append("another cow in the way")
    if area < GAIT_MIN_AREA:
        reasons.append("cow small in the frame")
    if info["side"] < SIDE_OK:
        reasons.append("not side-on")
    if not target.get("usable"):
        reasons.append(target.get("reason") or "skin model cannot use it")
    info["why"] = ", ".join(reasons)
    return info


def rank(infos):
    """Score the frames that have a cow (side-on-ness, sharpness against the sharpest, size, confidence)."""
    withcow = [i for i in infos if "sharp_box" in i]
    top = max((i["sharp_box"] for i in withcow), default=0.0) or 1.0
    ws, wsh, wsz, wc = WEIGHTS
    for i in withcow:
        i["score"] = ws * i["side"] + wsh * (i["sharp_box"] / top) + wsz * i["size"] + wc * i["conf"]
    return infos


def choose(infos):
    """Routing decision. -> {"skin": info|None, "face": info|None, "gait": [info], "decisions": [text], "drops": [text]}"""
    rank(infos)
    skin_c = [i for i in infos if i["skin_ok"]]
    skin = max(skin_c, key=lambda i: (i["score"], i["side"])) if skin_c else None
    faces = [i for i in infos if i["face"]]
    face = max(faces, key=lambda i: i["face"]["conf"]) if faces else None
    gait = []
    for i in sorted((i for i in infos if i["gait_ok"]), key=lambda i: -i["score"]):
        if all(abs(i["t"] - o["t"]) >= GAIT_GAP_S for o in gait):
            gait.append(i)
        if len(gait) == GAIT_FRAMES:
            break
    gait.sort(key=lambda i: i["t"])
    decisions, drops = [], []
    if face:
        decisions.append(f"Frame at {face['t']:.1f}s: a cow face is clear, so it goes to the cow-face model.")
    if skin:
        decisions.append(f"Frame at {skin['t']:.1f}s: cow clearly visible ({skin['view']}), so it goes to the skin model.")
    if gait:
        times = ", ".join("%.1fs" % g["t"] for g in gait)
        decisions.append(f"{len(gait)} side-on frame(s) ({times}): the cow is fully visible, "
                         "so they go to the pose model and the walking check.")
    for i in infos:
        if not (i is skin or i is face or i in gait):
            drops.append(f"{i['t']:.1f}s: {i['why'] or 'good, but another frame was better'}")
    return {"skin": skin, "face": face, "gait": gait, "decisions": decisions, "drops": drops}
