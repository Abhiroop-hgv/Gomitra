"""Offline test of the Raspberry Pi entry point /api/ingest and the frame agent (models run in-process). python test_ingest.py"""
import base64, os, tempfile
HERE = os.path.dirname(os.path.abspath(__file__))
os.environ.update(STORE="memory", INFER_BACKEND="local", EMBED_BACKEND="fake", ADMIN_KEY="k", DEVICE_KEY="dev",
                  SERVING_DIR=os.path.join(HERE, "..", "serving"))
import cv2
import numpy as np
from fastapi.testclient import TestClient
import agent
import main

c = TestClient(main.app)
S = os.path.join(HERE, "static", "samples")
D = {"x-device-key": "dev"}
b64 = lambda p: base64.b64encode(open(p, "rb").read()).decode()
sample = lambda n: os.path.join(S, n)

# ---- access and file types
assert c.post("/api/ingest", json={"file": b64(sample("walk_tharparkar.jpg"))}).status_code == 403
assert c.post("/api/ingest", json={"file": b64(sample("walk_tharparkar.jpg"))}, headers={"x-device-key": "no"}).status_code == 403
assert c.post("/api/ingest", json={"file": base64.b64encode(b"hello world, not a media file").decode()}, headers=D).status_code == 415

# ---- a close-up with no whole cow is looked at but reaches no model (the agent drops it)
r = c.post("/api/ingest", json={"file": b64(sample("lumpy_1.jpg")), "camera": "North field camera"}, headers=D)
assert r.status_code == 200, r.text
j = r.json(); print(j["summary"])
assert j["routed"] is False and "skin model" not in j["steps"] and j["decisions"], j

# ---- a clear side-on cow goes to the skin model
j = c.post("/api/ingest", json={"file": b64(sample("walk_tharparkar.jpg")), "camera": "North field camera"}, headers=D).json()
print(j["summary"]); print(*j["decisions"], sep="\n")
assert j["routed"] and "skin model" in j["steps"] and any("skin model" in d for d in j["decisions"]), j

# ---- sound
j = c.post("/api/ingest", json={"file": b64(sample("sound_distress.wav")), "camera": "North field camera"}, headers=D).json()
print(j["summary"], j["steps"])
assert j["kind"] == "audio" and "sound models" in j["steps"]

# ---- a short video with bad frames mixed in: the agent keeps the good ones and says why it dropped the rest
def letterbox(img, W=640, H=480):
    s = min(W / img.shape[1], H / img.shape[0])
    im = cv2.resize(img, (round(img.shape[1] * s), round(img.shape[0] * s)))
    out = np.zeros((H, W, 3), np.uint8); y, x = (H - im.shape[0]) // 2, (W - im.shape[1]) // 2
    out[y:y + im.shape[0], x:x + im.shape[1]] = im
    return out
rd = lambda n: letterbox(cv2.imread(sample(n)))
good = [rd("walk_lame.jpg"), rd("walk_sahiwal.jpg"), rd("walk_tharparkar.jpg")]
blurred = cv2.GaussianBlur(good[0], (0, 0), 25)
dark = (good[0] * 0.05).astype(np.uint8)
seq = [blurred] * 3 + [dark] * 3 + [rd("lumpy_1.jpg")] * 3 + [g for g in good for _ in range(3)]       # 3 frames each at 3 per second
path = os.path.join(tempfile.mkdtemp(), "t.mp4")
vw = cv2.VideoWriter(path, cv2.VideoWriter_fourcc(*"mp4v"), 3, (640, 480))
for f in seq:
    vw.write(f)
vw.release()
j = c.post("/api/ingest", json={"file": b64(path), "camera": "North field camera"}, headers=D).json()
print(j["summary"]); print(*j["decisions"], sep="\n")
assert j["kind"] == "video" and j["routed"], j
assert "blurred" in j["decisions"][0] and "dark" in j["decisions"][0] and "near-duplicate" in j["decisions"][0], j["decisions"][0]
assert any("side-on" in d and "pose model" in d for d in j["decisions"]), j["decisions"]

# ---- the walking/resting route: pretend one registered cow was recognised (stubs for the cow match and the pose model)
c.post("/api/demo/seed", headers={"x-admin-key": "k"})
real_analyze, calls = main.analyze, []
main.analyze = lambda a: {"faces_in_frame": 1, "results": [{"cow": {"id": "rani", "name": "Rani"}, "finding": None, "alert": False}]}
main.gait.analyze = lambda jpegs: (calls.append(len(jpegs)) or {"gait": {"score": 2, "summary": "stub"}, "posture": {"label": "lying"},
                                                               "overlay": None, "pose_used": True})
r1 = c.post("/api/ingest", json={"file": b64(path), "camera": "North field camera"}, headers=D).json()
assert "pose model" in r1["steps"] and r1["posture"] == "lying" and len(calls) == 1 and 1 <= calls[0] <= agent.GAIT_FRAMES, (r1, calls)
assert calls[0] == len([d for d in r1["decisions"] if "side-on frame" in d]) or calls[0] >= 1
r2 = c.post("/api/ingest", json={"file": b64(path)}, headers=D).json()
assert "pose model" not in r2["steps"] and len(calls) == 1, r2                        # at most one walking check per 10 minutes
assert c.get("/api/cows/rani/trends").json()["rest"]["samples"] == 1                  # the sighting was kept for the trends
main.analyze = real_analyze

# ---- the agent's pure rules, with made-up detector output
def info(w=640, h=480):
    return {"idx": 0, "t": 0.0, "w": w, "h": h, "img": np.full((h, w, 3), 120, np.uint8), "jpeg": b"x"}
def cow(box, conf=0.9, usable=True): return {"box": box, "cow_conf": conf, "usable": usable, "reason": ""}
a = agent.assess(info(), [cow([100, 120, 540, 400])], []); assert a["gait_ok"] and a["skin_ok"] and a["view"] == "side-on"
a = agent.assess(info(), [cow([0, 120, 440, 400])], []); assert not a["gait_ok"] and "cut off" in a["why"]            # touches the edge
a = agent.assess(info(), [cow([100, 120, 540, 400]), cow([120, 140, 500, 390])], []); assert not a["gait_ok"] and "in the way" in a["why"]
a = agent.assess(info(), [cow([250, 100, 390, 420])], []); assert not a["gait_ok"] and a["view"] != "side-on"         # facing the camera
a = agent.assess(info(), [cow([300, 200, 340, 230])], []); assert not a["gait_ok"] and not a["skin_ok"]              # tiny
a = agent.assess(info(), [], [{"usable": True, "conf": 0.8, "box": [1, 1, 2, 2]}]); assert a["face"] and a["view"] == "face"
print("ingest ok")
