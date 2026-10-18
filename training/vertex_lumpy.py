"""Run lumpy-skin inference on the DEPLOYED Vertex endpoint (token in env VTOKEN).
usage: python vertex_lumpy.py VIDEO.mp4 PHOTO_ROOT   (PHOTO_ROOT holds healthy/ lumpy/ foot-and-mouth/)
"""
import base64, glob, json, os, random, sys, time, urllib.request
import cv2

video, root = sys.argv[1:3]
URL = "https://asia-south1-aiplatform.googleapis.com/v1/projects/cattle-id-511705/locations/asia-south1/endpoints/4319921811904004096:predict"
TOKEN = os.environ["VTOKEN"]


def jpg_b64(img, maxside=720):
    h, w = img.shape[:2]
    s = min(1.0, maxside / max(h, w))
    if s < 1:
        img = cv2.resize(img, (round(w * s), round(h * s)), interpolation=cv2.INTER_AREA)
    return base64.b64encode(cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 85])[1].tobytes()).decode()


items = []  # (label, b64)
cap = cv2.VideoCapture(video); n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
for k in range(1, 11):
    cap.set(cv2.CAP_PROP_POS_FRAMES, n * k // 11); ok, f = cap.read()
    if ok: items.append((f"video frame {n * k // 11}", jpg_b64(f)))
random.seed(1)
for folder, name in [("healthy", "photo healthy"), ("lumpy", "photo lumpy"), ("foot-and-mouth", "photo fmd")]:
    files = sorted(glob.glob(os.path.join(root, folder, "*.*")))
    for p in random.sample(files, 5):
        img = cv2.imread(p)
        if img is not None: items.append((f"{name}: {os.path.basename(p)[:28]}", jpg_b64(img)))


def call(batch):
    body = json.dumps({"instances": [{"task": "lumpy", "image_b64": b, "meta": {"label": l}} for l, b in batch]}).encode()
    req = urllib.request.Request(URL, data=body, headers={"Authorization": "Bearer " + TOKEN, "Content-Type": "application/json"})
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=300) as r:
        return json.loads(r.read())["predictions"], time.time() - t0, len(body)


for i in range(0, len(items), 5):
    preds, dt, size = call(items[i:i + 5])
    print(f"-- request of {len(preds)} images, {size // 1024} KB, {dt:.1f}s")
    for p in preds:
        lab = p["meta"]["label"]
        if p.get("error"): print(f"  {lab:42s} ERROR {p['error']}"); continue
        if not p["cows"]: print(f"  {lab:42s} no cow found"); continue
        for c in p["cows"]:
            r = ("%s lumpy=%.2f normal=%.2f fmd=%.2f" % ("", c["probs"]["lumpy"], c["probs"]["normal"], c["probs"]["fmd"])) if c["usable"] else "skipped: " + c["reason"]
            print(f"  {lab:42s} {r}")
