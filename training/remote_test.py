"""Call the deployed server: python remote_test.py URL TOKEN VIDEO.mp4  (token from gcloud auth print-identity-token)"""
import base64, io, json, sys, time, urllib.request
import cv2, numpy as np, soundfile as sf

url, token, video = sys.argv[1:4]
cap = cv2.VideoCapture(video); cap.set(cv2.CAP_PROP_POS_FRAMES, 150); _, f = cap.read()
b64 = lambda b: base64.b64encode(b).decode()
jpg = b64(cv2.imencode(".jpg", f, [cv2.IMWRITE_JPEG_QUALITY, 85])[1].tobytes())
t = np.linspace(0, 3, 3 * 22050, endpoint=False)
wav = (0.2 * np.sin(2 * np.pi * 600 * t) + 0.05 * np.random.default_rng(0).standard_normal(t.size)).astype(np.float32)
buf = io.BytesIO(); sf.write(buf, wav, 22050, format="WAV")
body = json.dumps({"instances": [{"task": "lumpy", "image_b64": jpg, "meta": {"camera": "side-1"}},
                                 {"task": "audio", "audio_b64": b64(buf.getvalue())}]}).encode()

def call(path, data=None):
    req = urllib.request.Request(url + path, data=data, headers={"Authorization": "Bearer " + token, "Content-Type": "application/json"})
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=300) as r:
            return r.status, time.time() - t0, r.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, time.time() - t0, e.read().decode()[:300]

for i in range(40):                       # cold start: wait for models to finish loading
    s, dt, txt = call("/health")
    print(f"health try {i}: {s} ({dt:.1f}s) {txt[:80]}")
    if s == 200: break
    time.sleep(5)
s, dt, txt = call("/predict", body)
print("predict:", s, f"{dt:.1f}s")
print(txt[:1500])
