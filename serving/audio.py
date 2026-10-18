"""Cattle audio models from the CattlePlus repo (shashi007-hub/livestock-monitoring).

Preprocessing is copied from that repo's backend/worker/app/mapping.py; it must match what the
models were trained with, so do not change it without the model's author.
  - distress (cow_model.onnx): log-mel 90 bands -> 200x90 image; output = P(HFC). HFC triggers their distress alert.
  - bite/chew (xgb_model.onnx): 13 MFCC x 128 frames flattened (1664); labels chew / bite / chew-bite.
"""
import io
import os
import numpy as np
import librosa
import onnxruntime as ort
from PIL import Image

SR = 22050
BITE_CHEW = {0: "chew", 1: "bite", 2: "chew-bite"}


def _session(path):
    opts = ort.SessionOptions()
    opts.intra_op_num_threads = int(os.getenv("ORT_THREADS", "2"))
    return ort.InferenceSession(path, opts, providers=["CPUExecutionProvider"])


class Audio:
    def __init__(self, model_dir):
        self.distress = _session(os.path.join(model_dir, "cow_model.onnx"))
        self.chew = _session(os.path.join(model_dir, "xgb_model.onnx"))

    @staticmethod
    def load(wav_bytes):
        y, _ = librosa.load(io.BytesIO(wav_bytes), sr=SR)
        return y

    def _distress(self, y):
        mel = librosa.feature.melspectrogram(y=y, sr=SR, n_fft=2048, hop_length=512, n_mels=90)
        db = librosa.power_to_db(mel)
        norm = (librosa.util.normalize(db) * 255).astype(np.uint8)
        img = np.array(Image.fromarray(norm).resize((90, 200), Image.Resampling.LANCZOS))
        x = np.repeat(img[..., None], 3, axis=-1)[None].astype(np.float32)
        score = float(self.distress.run(None, {self.distress.get_inputs()[0].name: x})[0][0][0])
        return {"label": "HFC" if score >= 0.5 else "LFC", "distress": score >= 0.5, "p_hfc": round(score, 4)}

    def _chew(self, y):
        m = librosa.feature.mfcc(y=y, sr=SR, n_mfcc=13, hop_length=256, n_fft=1024).astype(np.float32)
        m = np.pad(m, ((0, 0), (0, 128 - m.shape[1]))) if m.shape[1] < 128 else m[:, :128]
        out = self.chew.run(None, {self.chew.get_inputs()[0].name: m.flatten()[None].astype(np.float32)})
        probs = out[1][0]
        return {"label": BITE_CHEW.get(int(out[0][0]), "unknown"),
                "probs": {BITE_CHEW[i]: round(float(p), 4) for i, p in enumerate(probs)}}

    def predict(self, wav_bytes):
        y = self.load(wav_bytes)
        seconds = len(y) / SR
        rms = float(np.sqrt(np.mean(y ** 2))) if len(y) else 0.0
        if seconds < 0.5:
            return {"usable": False, "reason": "too_short", "seconds": round(seconds, 2)}
        if rms < 1e-4:
            return {"usable": False, "reason": "silent", "seconds": round(seconds, 2)}
        return {"usable": True, "seconds": round(seconds, 2), "rms": round(rms, 5),
                "distress": self._distress(y), "bite_chew": self._chew(y)}
