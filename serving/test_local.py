"""Smoke test of the Vertex server in-process: python test_local.py VIDEO.mp4

Plumbing only: checks shapes, routes and error handling. The synthetic audio says NOTHING about audio accuracy.
"""
import base64, io, sys, time
import cv2, numpy as np, soundfile as sf
from fastapi.testclient import TestClient
import app as server

video = sys.argv[1]
cap = cv2.VideoCapture(video); frames = []
for n in (30, 150, 300):
    cap.set(cv2.CAP_PROP_POS_FRAMES, n); ok, f = cap.read()
    if ok: frames.append(f)
b64 = lambda b: base64.b64encode(b).decode()
jpgs = [b64(cv2.imencode(".jpg", f, [cv2.IMWRITE_JPEG_QUALITY, 85])[1].tobytes()) for f in frames]
print("frame JPEG sizes (KB):", [len(j) * 3 // 4 // 1024 for j in jpgs], "(Vertex request limit is about 1.5 MB, to be verified)")

rng = np.random.default_rng(0); t = np.linspace(0, 3, 3 * 22050, endpoint=False)
wav = (0.2 * np.sin(2 * np.pi * 600 * t) + 0.05 * rng.standard_normal(t.size)).astype(np.float32)
buf = io.BytesIO(); sf.write(buf, wav, 22050, format="WAV"); wav_b64 = b64(buf.getvalue())
print("3 s wav (KB):", len(buf.getvalue()) // 1024)

with TestClient(server.app) as c:
    for _ in range(60):
        if c.get("/health").status_code == 200: break
        time.sleep(1)
    print("health:", c.get("/health").status_code)
    inst = [{"task": "lumpy", "image_b64": j, "meta": {"camera": "side-1", "i": i}} for i, j in enumerate(jpgs)]
    inst += [{"task": "audio", "audio_b64": wav_b64, "meta": {"camera": "side-1"}},
             {"task": "lumpy", "image_b64": "bm90IGFuIGltYWdl"},
             {"task": "bogus"}]
    t0 = time.time(); r = c.post("/predict", json={"instances": inst}); dt = time.time() - t0
    print("status", r.status_code, f"{dt:.2f}s for {len(inst)} instances")
    for p in r.json()["predictions"]:
        if p.get("error"): print(" ", p["task"], "ERROR:", p["error"])
        elif p["task"] == "lumpy":
            print("  lumpy frame", p["meta"]["i"], "cows:", [(x["box"], x.get("probs") or x["reason"]) for x in p["cows"]][:3])
        else: print("  audio:", p)
