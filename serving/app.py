"""Vertex AI custom-container server.

Vertex sends  POST <AIP_PREDICT_ROUTE>  {"instances": [...]}  and expects  {"predictions": [...]}.
Each instance is independent, so one bad frame never fails the whole batch:
    {"task": "lumpy", "image_b64": "<jpeg/png bytes, base64>"}        CCTV frame: detect cows, classify each crop
    {"task": "lumpy_photo", "image_b64": "..."}                          farmer photo: classify the whole image
    {"task": "identify", "image_b64": "...", "read_tags": false}         cow faces + embeddings (+ ear-tag OCR if asked)
    {"task": "audio", "audio_b64": "<wav bytes, base64>"}
Camera/zone/time metadata is the router's business; it is passed through untouched as "meta".

Model files: ./models by default, MODEL_DIR to override, or the gs:// folder in AIP_STORAGE_URI
(Vertex sets that when the Model was uploaded with an artifact URI).
"""
import base64
import os
import threading
from contextlib import asynccontextmanager

import cv2
import numpy as np
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

NEEDED = ["yolo11n.onnx", "lsd_v2_3class.onnx", "cow_model.onnx", "xgb_model.onnx",
          "face_tag_detector.onnx", "face_embedder.onnx"]
state = {"vision": None, "audio": None, "identify": None, "error": None}


def ready():
    return all(state[k] is not None for k in ("vision", "audio", "identify"))


def model_dir():
    uri = os.getenv("AIP_STORAGE_URI", "")
    if uri.startswith("gs://"):
        from google.cloud import storage
        bucket, _, prefix = uri[5:].partition("/")
        dest = "/tmp/models"
        os.makedirs(dest, exist_ok=True)
        client = storage.Client()
        for name in NEEDED:
            client.bucket(bucket).blob(f"{prefix.rstrip('/')}/{name}".lstrip("/")).download_to_filename(f"{dest}/{name}")
        return dest
    return os.getenv("MODEL_DIR", os.path.join(os.path.dirname(__file__), "models"))


def load():
    try:
        from vision import Vision
        from audio import Audio
        from identify import Identify
        d = model_dir()
        v, a, i = Vision(d), Audio(d), Identify(d)
        noise = np.random.default_rng(0).standard_normal(22050 * 3).astype(np.float32) * 0.05
        a._distress(noise); a._chew(noise)               # first librosa call compiles numba code (~1 min): do it before /health says ok
        v.predict(np.zeros((480, 640, 3), np.uint8))
        i.predict(np.zeros((480, 640, 3), np.uint8))
        state["vision"], state["audio"], state["identify"] = v, a, i
    except Exception as e:  # keep serving /health as 503 so the failure is visible in logs
        state["error"] = repr(e)
        raise


@asynccontextmanager
async def lifespan(_):
    threading.Thread(target=load, daemon=True).start()   # port opens at once; /health stays 503 until ready
    yield


app = FastAPI(lifespan=lifespan)


class Req(BaseModel):
    instances: list[dict]
    parameters: dict | None = None


def one(inst):
    task = inst.get("task")
    out = {"task": task, "meta": inst.get("meta")}
    try:
        if task in ("lumpy", "lumpy_photo", "identify"):  # lumpy = CCTV frame (finds cows first); lumpy_photo = whole farmer photo
            buf = np.frombuffer(base64.b64decode(inst["image_b64"]), np.uint8)
            bgr = cv2.imdecode(buf, cv2.IMREAD_COLOR)
            if bgr is None:
                raise ValueError("image could not be decoded")
            rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
            if task == "identify":
                out.update(state["identify"].predict(rgb, read_tags=bool(inst.get("read_tags", False))))
            else:
                out.update(state["vision"].predict(rgb) if task == "lumpy" else state["vision"].predict_photo(rgb))
        elif task == "audio":
            out.update(state["audio"].predict(base64.b64decode(inst["audio_b64"])))
        else:
            raise ValueError(f"unknown task {task!r}")
    except Exception as e:
        out["error"] = f"{type(e).__name__}: {e}"
    return out


def health():
    if not ready():
        raise HTTPException(503, state["error"] or "models loading")
    return {"status": "ok"}


def predict(req: Req):
    if not ready():
        raise HTTPException(503, "models loading")
    return {"predictions": [one(i) for i in req.instances]}


for route in {os.getenv("AIP_HEALTH_ROUTE", "/health"), "/health"}:
    app.add_api_route(route, health, methods=["GET"])
for route in {os.getenv("AIP_PREDICT_ROUTE", "/predict"), "/predict"}:
    app.add_api_route(route, predict, methods=["POST"])

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("AIP_HTTP_PORT", "8080")))
