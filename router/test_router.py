"""Offline test of the router: in-memory store, models run in-process (no cloud), Gemini falls back to templates.
python test_router.py PHOTO_ROOT     (PHOTO_ROOT has healthy/ lumpy/ foot-and-mouth/ folders)
"""
import base64, glob, os, sys, io, wave
os.environ.update(STORE="memory", INFER_BACKEND="local", EMBED_BACKEND="fake", ADMIN_KEY="k",
                  SERVING_DIR=os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "serving"))
import numpy as np
from fastapi.testclient import TestClient
import main

root = sys.argv[1]
def pic(folder, i=0):
    p = sorted(glob.glob(os.path.join(root, folder, "*.*")))[i]
    return "data:image/jpeg;base64," + base64.b64encode(open(p, "rb").read()).decode()

c = TestClient(main.app)
H = {"x-admin-key": "k"}
print("seed", c.post("/api/demo/seed", headers=H).json())
print("status", c.get("/api/status").json())

# 1. farmer photo of a lumpy cow, cow chosen by the farmer
r = c.post("/api/analyze", json={"image": pic("lumpy"), "mode": "photo", "cow_id": "gauri"}).json()
x = r["results"][0]
print("lumpy photo ->", x["probs"], "| finding", x["finding"], "| alert", x["alert"], "|", (x["message"] or {}).get("en"))
# 2. healthy photo
r = c.post("/api/analyze", json={"image": pic("healthy"), "mode": "photo", "cow_id": "rani"}).json()
x = r["results"][0]; print("healthy photo ->", x["probs"], "| alert", x["alert"])
# 3. FMD photo
r = c.post("/api/analyze", json={"image": pic("foot-and-mouth"), "mode": "photo", "cow_id": "nandini"}).json()
x = r["results"][0]; print("fmd photo ->", x["probs"], "| finding", x["finding"], "| alert", x["alert"])
# 4. herd list
print([(k["name"], k["alert"], k.get("kind")) for k in c.get("/api/cows").json()][:4])
# 5. resolve
print("resolve", c.post("/api/cows/gauri/resolve").json(), c.get("/api/cows/gauri").json()["alert"])
# 6. register a new cow from 4 healthy photos
photos = {k: pic("healthy", i) for i, k in enumerate(("front", "left", "right", "back"))}
reg = c.post("/api/cows", json={"name": "Test", "tag": "0999", "breed": "Gir", "age": "4", "photos": photos}).json()
print("register ->", reg["cow"]["id"], "faces_found", reg["faces_found"], reg["warning"])
# 7. audio (synthetic noise 5 s)
buf = io.BytesIO()
with wave.open(buf, "wb") as w:
    w.setnchannels(1); w.setsampwidth(2); w.setframerate(22050)
    w.writeframes((np.random.default_rng(1).standard_normal(22050 * 5) * 3000).astype("<i2").tobytes())
a = c.post("/api/audio", json={"audio": base64.b64encode(buf.getvalue()).decode(), "camera": "North field camera"}).json()
print("audio ->", {k: a["audio"].get(k) for k in ("usable", "distress", "bite_chew")}, "| alert", bool(a["alert"]), a["note"])
print("feeding", c.get("/api/feeding", params={"camera": "North field camera"}).json())
# 8. knowledge base + ask (fake embeddings, Gemini will fail offline -> 502 is expected here)
print("kb add", c.post("/api/admin/kb", headers=H, json={"source": "test-doc", "text": "Lumpy skin disease spreads by biting flies. Isolate sick cattle and call the vet."}).json())
print("ask ->", c.post("/api/ask", json={"question": "what is lumpy skin disease", "lang": "en"}).status_code)
