"""Lumpy-skin screening on ONE frame: find cows (YOLO11n ONNX), classify each crop (EfficientNet-B0 ONNX).

Stateless on purpose: Vertex endpoints keep no memory between calls, so voting over many frames
happens in the caller (Cloud Run + Firestore), not here.
"""
import os
import cv2
import numpy as np
import onnxruntime as ort

CLASSES = ["normal", "lumpy", "fmd"]
COW = 19                      # COCO class id for 'cow'
MIN_SIDE, MIN_SHARP = 80, 20.0  # same crop-quality gate as training/predict_video.py
MEAN = np.array([0.485, 0.456, 0.406], np.float32)
STD = np.array([0.229, 0.224, 0.225], np.float32)


def _session(path):
    opts = ort.SessionOptions()
    opts.intra_op_num_threads = int(os.getenv("ORT_THREADS", "2"))
    return ort.InferenceSession(path, opts, providers=["CPUExecutionProvider"])


class Vision:
    def __init__(self, model_dir):
        self.det = _session(os.path.join(model_dir, "yolo11n.onnx"))
        self.clf = _session(os.path.join(model_dir, "lsd_v2_3class.onnx"))

    def detect_cows(self, rgb, conf=0.3, iou=0.5):
        h, w = rgb.shape[:2]
        s = 640 / max(h, w)
        nh, nw = round(h * s), round(w * s)
        canvas = np.full((640, 640, 3), 114, np.uint8)
        top, left = (640 - nh) // 2, (640 - nw) // 2
        canvas[top:top + nh, left:left + nw] = cv2.resize(rgb, (nw, nh))
        x = (canvas.astype(np.float32) / 255).transpose(2, 0, 1)[None]
        out = self.det.run(None, {"images": x})[0][0]          # (84, 8400): cx, cy, w, h, 80 class scores
        scores = out[4 + COW]
        keep = scores >= conf
        if not keep.any():
            return []
        b, sc = out[:4, keep].T, scores[keep]
        xywh = np.stack([b[:, 0] - b[:, 2] / 2, b[:, 1] - b[:, 3] / 2, b[:, 2], b[:, 3]], 1)
        idx = cv2.dnn.NMSBoxes(xywh.tolist(), sc.tolist(), conf, iou)
        boxes = []
        for i in np.array(idx).reshape(-1):
            x0, y0, bw, bh = xywh[i]
            x1 = int(np.clip((x0 - left) / s, 0, w)); y1 = int(np.clip((y0 - top) / s, 0, h))
            x2 = int(np.clip((x0 + bw - left) / s, 0, w)); y2 = int(np.clip((y0 + bh - top) / s, 0, h))
            boxes.append((x1, y1, x2, y2, float(sc[i])))
        return boxes

    def _prep(self, crop):
        interp = cv2.INTER_AREA if min(crop.shape[:2]) > 224 else cv2.INTER_LINEAR
        img = cv2.resize(crop, (224, 224), interpolation=interp).astype(np.float32) / 255
        return ((img - MEAN) / STD).transpose(2, 0, 1)

    def predict_photo(self, rgb):
        """Farmer-uploaded photo (often a close-up of skin or face): classify the WHOLE image.

        The classifier was trained on whole photos, so no cow box is needed. Do not use this for CCTV frames:
        an empty yard would still get a label. cows_detected is returned as context only.
        """
        h, w = rgb.shape[:2]
        out = {"usable": False, "reason": "", "cows_detected": len(self.detect_cows(rgb))}
        if min(h, w) < MIN_SIDE:
            out["reason"] = "too_small"
        elif cv2.Laplacian(cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY), cv2.CV_64F).var() < MIN_SHARP:
            out["reason"] = "blurry"
        else:
            logits = self.clf.run(None, {"input": self._prep(rgb)[None].astype(np.float32)})[0][0]
            p = np.exp(logits - logits.max()); p /= p.sum()
            out["usable"] = True
            out["probs"] = {c: round(float(v), 4) for c, v in zip(CLASSES, p)}
        return {"photo": out}

    def predict(self, rgb):
        cows, batch, slots = [], [], []
        for x1, y1, x2, y2, c in self.detect_cows(rgb):
            crop = rgb[y1:y2, x1:x2]
            item = {"box": [x1, y1, x2, y2], "cow_conf": round(c, 3), "usable": False, "reason": ""}
            if crop.size == 0 or min(crop.shape[:2]) < MIN_SIDE:
                item["reason"] = "too_small"
            elif cv2.Laplacian(cv2.cvtColor(crop, cv2.COLOR_RGB2GRAY), cv2.CV_64F).var() < MIN_SHARP:
                item["reason"] = "blurry"
            else:
                batch.append(self._prep(crop)); slots.append(item)
            cows.append(item)
        if batch:
            logits = self.clf.run(None, {"input": np.stack(batch).astype(np.float32)})[0]
            p = np.exp(logits - logits.max(1, keepdims=True)); p /= p.sum(1, keepdims=True)
            for item, row in zip(slots, p):
                item["usable"] = True
                item["probs"] = {c: round(float(v), 4) for c, v in zip(CLASSES, row)}
        return {"cows": cows}
