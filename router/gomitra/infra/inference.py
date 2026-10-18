"""Client for the model-serving container (serving/app.py).

INFER_BACKEND picks where the models run, so the same router works with any of them:
  vertex    Vertex AI endpoint (ENDPOINT_ID, REGION, PROJECT)       billed while deployed
  cloudrun  the same container on Cloud Run (SERVING_URL)           scales to zero
  local     imports serving/app.py in-process (SERVING_DIR)         laptop tests only
Every call sends {"instances": [...]} and gets {"predictions": [...]} back, like Vertex does.
"""
import base64
import os

import cv2
import numpy as np

from gomitra.core import tracing as trace
BACKEND = os.getenv("INFER_BACKEND", "cloudrun")
PROJECT = os.getenv("PROJECT", "cattle-id-511705")
REGION = os.getenv("REGION", "asia-south1")
ENDPOINT_ID = os.getenv("ENDPOINT_ID", "")
SERVING_URL = os.getenv("SERVING_URL", "").rstrip("/")
MAX_SIDE = 1024            # Vertex rejects very large requests (about 1.5 MB), so frames are shrunk first


def shrink_jpeg(raw: bytes, max_side: int = MAX_SIDE, quality: int = 85) -> bytes:
    """Any image bytes -> JPEG no larger than max_side on its long edge."""
    img = cv2.imdecode(np.frombuffer(raw, np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError("image could not be decoded")
    h, w = img.shape[:2]
    s = min(1.0, max_side / max(h, w))
    if s < 1:
        img = cv2.resize(img, (round(w * s), round(h * s)), interpolation=cv2.INTER_AREA)
    return cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, quality])[1].tobytes()


def b64(raw: bytes) -> str:
    return base64.b64encode(raw).decode()


class Infer:
    def __init__(self):
        self._session = None
        self._local = None

    # -- transports ---------------------------------------------------------------------------
    def _auth_session(self):
        if self._session is None:
            import google.auth
            from google.auth.transport.requests import AuthorizedSession
            creds, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
            self._session = AuthorizedSession(creds)
        return self._session

    def _post_vertex(self, instances):
        url = (f"https://{REGION}-aiplatform.googleapis.com/v1/projects/{PROJECT}/locations/{REGION}"
               f"/endpoints/{ENDPOINT_ID}:predict")
        r = self._auth_session().post(url, json={"instances": instances}, timeout=120)
        r.raise_for_status()
        return r.json()["predictions"]

    def _post_cloudrun(self, instances):
        import google.auth.transport.requests as gtr
        import google.oauth2.id_token as idt
        import requests
        token = idt.fetch_id_token(gtr.Request(), SERVING_URL)      # service-to-service: the service is private
        r = requests.post(f"{SERVING_URL}/predict", json={"instances": instances},
                          headers={"Authorization": f"Bearer {token}"}, timeout=300)
        r.raise_for_status()
        return r.json()["predictions"]

    def _post_local(self, instances):
        if self._local is None:
            import sys, time
            sys.path.insert(0, os.environ["SERVING_DIR"])
            import app as serving
            threading_started = serving.threading.Thread(target=serving.load, daemon=True)
            threading_started.start()
            for _ in range(240):
                if serving.ready():
                    break
                time.sleep(1)
            self._local = serving
        return [self._local.one(i) for i in instances]

    def predict(self, instances):
        fn = {"vertex": self._post_vertex, "cloudrun": self._post_cloudrun, "local": self._post_local}[BACKEND]
        service, detail = {
            "vertex": ("Vertex AI endpoint", f"online prediction, {REGION}, endpoint {ENDPOINT_ID}"),
            "cloudrun": ("Cloud Run (cattle-serving)", f"model container, {REGION}"),
            "local": ("Local models", "laptop test")}[BACKEND]
        tasks = sorted({i.get("task", "?") for i in instances})
        with trace.step(service, f"{detail}, task: {', '.join(tasks)}"):
            return fn(instances)

    # -- tasks --------------------------------------------------------------------------------
    def vision(self, jpeg: bytes, cctv: bool = False, read_tags: bool = False):
        """One image -> (lumpy result, identify result). Both models see the same picture."""
        img = b64(jpeg)
        lumpy, ident = self.predict([
            {"task": "lumpy" if cctv else "lumpy_photo", "image_b64": img},
            {"task": "identify", "image_b64": img, "read_tags": read_tags},
        ])
        return lumpy, ident

    def identify(self, jpeg: bytes):
        return self.predict([{"task": "identify", "image_b64": b64(jpeg)}])[0]

    def audio(self, wav: bytes):
        return self.predict([{"task": "audio", "audio_b64": b64(wav)}])[0]
