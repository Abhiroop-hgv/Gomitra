"""Pose + posture service. POST /pose {"images": [base64 jpeg, ...]} -> keypoints, standing/sitting/lying, overlay image."""
import base64
import time
from dataclasses import asdict

import cv2
import numpy as np
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

import activity_monitoring as am
import pose_estimation as pe

app = FastAPI()
backend = pe.SuperAnimalBackend()
MAX_FRAMES, MAX_SIDE, MIN_CONF = 5, 960, 0.3
SKELETON = (("nose", "neck_base"), ("neck_base", "back_middle"), ("back_middle", "tail_base"),
            ("front_left_thigh", "front_left_knee"), ("front_left_knee", "front_left_paw"),
            ("front_right_thigh", "front_right_knee"), ("front_right_knee", "front_right_paw"),
            ("hind_left_thigh", "hind_left_knee"), ("hind_left_knee", "hind_left_paw"),
            ("hind_right_thigh", "hind_right_knee"), ("hind_right_knee", "hind_right_paw"))


class Req(BaseModel):
    images: list[str]


def overlay(frame, pose):
    img = frame.copy()
    scale = max(img.shape[:2]) / 480.0
    radius, thick = max(2, int(round(3 * scale))), max(1, int(round(1.5 * scale)))
    for a, b in SKELETON:
        if a in pose and b in pose and pose[a][2] >= MIN_CONF and pose[b][2] >= MIN_CONF:
            cv2.line(img, (int(pose[a][0]), int(pose[a][1])), (int(pose[b][0]), int(pose[b][1])), (0, 220, 255), thick, cv2.LINE_AA)
    for x, y, c in pose.values():
        cv2.circle(img, (int(x), int(y)), radius if c >= MIN_CONF else max(1, radius - 1), (0, 200, 0) if c >= MIN_CONF else (0, 0, 255), -1, cv2.LINE_AA)
    return img


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/pose")
def pose(req: Req):
    if not req.images:
        raise HTTPException(400, "no images")
    frames = []
    for s in req.images[:MAX_FRAMES]:
        f = cv2.imdecode(np.frombuffer(base64.b64decode(s.split(",", 1)[-1]), np.uint8), cv2.IMREAD_COLOR)
        if f is None:
            raise HTTPException(400, "image could not be decoded")
        frames.append(f)
    h, w = frames[0].shape[:2]
    k = min(1.0, MAX_SIDE / max(h, w))
    size = (round(w * k), round(h * k))
    frames = [cv2.resize(f, size, interpolation=cv2.INTER_AREA) for f in frames]      # DeepLabCut needs equal sizes
    t = time.time()
    poses = backend.estimate_frames(frames)
    posture = [asdict(am.classify_pose(p)) for p in poses]
    best = max(range(len(poses)), key=lambda i: sum(1 for v in poses[i].values() if v[2] >= MIN_CONF))
    ok, buf = cv2.imencode(".jpg", overlay(frames[best], poses[best]), [cv2.IMWRITE_JPEG_QUALITY, 82])
    return {"size": list(size), "seconds": round(time.time() - t, 1), "best": best,
            "poses": [{k2: [round(v[0], 1), round(v[1], 1), round(v[2], 3)] for k2, v in p.items()} for p in poses],
            "posture": posture, "overlay_b64": base64.b64encode(buf.tobytes()).decode()}
