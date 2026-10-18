"""Compare CCTV mode ('lumpy') with whole-photo mode ('lumpy_photo') on labelled photos.
python test_photo.py PHOTO_ROOT [per_class]
NOTE: most of these photos were in the training set, so accuracy here is inflated: use it to compare modes, not as a result.
"""
import base64, glob, os, random, sys, time
import cv2, numpy as np
from fastapi.testclient import TestClient
import app as server

root = sys.argv[1]; per = int(sys.argv[2]) if len(sys.argv) > 2 else 40
CLS = {"healthy": "normal", "lumpy": "lumpy", "foot-and-mouth": "fmd"}
random.seed(7)
data = []
for folder, label in CLS.items():
    files = sorted(glob.glob(os.path.join(root, folder, "*.*"))); random.shuffle(files)
    for p in files[:per]:
        img = cv2.imread(p)
        if img is None: continue
        h, w = img.shape[:2]; s = min(1.0, 720 / max(h, w))
        if s < 1: img = cv2.resize(img, (round(w * s), round(h * s)), interpolation=cv2.INTER_AREA)
        data.append((label, base64.b64encode(cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 85])[1].tobytes()).decode()))

def top(probs): return max(probs, key=probs.get)

with TestClient(server.app) as c:
    for _ in range(90):
        if c.get("/health").status_code == 200: break
        time.sleep(1)
    res = {"cctv": [], "photo": []}
    for i in range(0, len(data), 10):
        chunk = data[i:i + 10]
        for mode, task in (("cctv", "lumpy"), ("photo", "lumpy_photo")):
            r = c.post("/predict", json={"instances": [{"task": task, "image_b64": b} for _, b in chunk]}).json()["predictions"]
            for (lab, _), p in zip(chunk, r):
                if mode == "cctv":
                    ok = [x for x in p["cows"] if x["usable"]]
                    pred = top({k: np.mean([x["probs"][k] for x in ok]) for k in ok[0]["probs"]}) if ok else None  # mean over crops
                else:
                    pred = top(p["photo"]["probs"]) if p["photo"]["usable"] else None
                res[mode].append((lab, pred))
    n = len(data)
    print(f"{n} images ({per} per class)")
    for mode in ("cctv", "photo"):
        got = [(l, p) for l, p in res[mode] if p]
        right = sum(l == p for l, p in got)
        print(f"{mode:6s}: classified {len(got)}/{n} ({len(got)/n:.0%}); correct among classified {right}/{len(got)} ({right/max(len(got),1):.0%}); correct of all {right/n:.0%}")
    for lab in ("normal", "lumpy", "fmd"):
        for mode in ("cctv", "photo"):
            rows = [(l, p) for l, p in res[mode] if l == lab]
            print(f"   {lab:7s} {mode:6s} classified {sum(1 for _, p in rows if p):2d}/{len(rows)}  correct {sum(1 for l, p in rows if p == l):2d}")
