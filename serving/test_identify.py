"""Run the 'identify' task through the server on photos that contain faces. python test_identify.py PHOTO_ROOT"""
import base64, glob, os, random, sys, time
import cv2, numpy as np
from fastapi.testclient import TestClient
import app as server
root = sys.argv[1]; random.seed(3); files = []
for f in os.listdir(root): files += random.sample(sorted(glob.glob(os.path.join(root, f, "*.*"))), 60)
def b64(p):
    img = cv2.imread(p); h, w = img.shape[:2]; s = min(1.0, 1280 / max(h, w))
    if s < 1: img = cv2.resize(img, (round(w * s), round(h * s)), interpolation=cv2.INTER_AREA)
    return base64.b64encode(cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 90])[1].tobytes()).decode()
with TestClient(server.app) as c:
    for _ in range(120):
        if c.get("/health").status_code == 200: break
        time.sleep(1)
    print("health", c.get("/health").status_code)
    hits = []
    for i in range(0, len(files), 12):
        batch = files[i:i + 12]
        r = c.post("/predict", json={"instances": [{"task": "identify", "image_b64": b64(p)} for p in batch]}).json()["predictions"]
        hits += [(p, x) for p, x in zip(batch, r) if x.get("faces") or x.get("tags_in_frame")]
    print(len(hits), "of", len(files), "images had a face or tag")
    for p, x in hits[:6]:
        print(" ", os.path.basename(p)[:30], "faces:", [(f["conf"], f["usable"], f["reason"], len(f.get("embedding", [])), len(f["tags"])) for f in x["faces"]], "tags_in_frame", x["tags_in_frame"])
    tagged = [p for p, x in hits if any(f["tags"] for f in x["faces"])]
    if tagged:
        t0 = time.time(); r = c.post("/predict", json={"instances": [{"task": "identify", "image_b64": b64(tagged[0]), "read_tags": True}]}).json()["predictions"][0]
        print("OCR on", os.path.basename(tagged[0])[:30], f"({time.time()-t0:.1f}s):", [t.get("read") for f in r["faces"] for t in f["tags"]])
    if hits:
        f = next((f for _, x in hits for f in x["faces"] if f["usable"]), None)
        if f: print("embedding length", len(f["embedding"]), "norm", round(float(np.linalg.norm(f["embedding"])), 4))
