"""Cow face / ear-tag identification step, ONNX port of the `cattle_id` repo (Abhiroop-hgv/Cattle-detection).

Stateless on purpose. This finds faces and ear tags in ONE frame and returns each face's 256-d embedding
(L2-normalised) plus any tag numbers read. Matching an embedding against registered cows, voting over frames
and storing cows are the caller's job (Cloud Run + Firestore), because a Vertex endpoint keeps no memory.

Constants and preprocessing mirror cattle_id/config.py, detector.py, embedder.py, quality.py, tagreader.py.
"""
import os
import re
import cv2
import numpy as np
import onnxruntime as ort
from PIL import Image

FACE, EAR_TAG = 0, 1                       # detector class ids: cow_face, ear_tag
FACE_CONF, IMGSZ, IOU = 0.5, 640, 0.7
FACE_PAD, TAG_PAD, TAG_NEAR = 0.1, 0.15, 0.6
MIN_SIDE, MIN_SHARP = 48, 40.0             # quality gate for face crops
TAG_MAX_READS, TAG_MIN_DIGITS, TAG_MAX_DIGITS, TAG_MIN_CONF = 5, 3, 6, 0.5
MEAN = np.array([0.485, 0.456, 0.406], np.float32)
STD = np.array([0.229, 0.224, 0.225], np.float32)


def _session(path):
    opts = ort.SessionOptions()
    opts.intra_op_num_threads = int(os.getenv("ORT_THREADS", "2"))
    return ort.InferenceSession(path, opts, providers=["CPUExecutionProvider"])


def sharpness(gray):
    g = gray.astype(np.float32)
    return float((-4 * g[1:-1, 1:-1] + g[:-2, 1:-1] + g[2:, 1:-1] + g[1:-1, :-2] + g[1:-1, 2:]).var())


class Identify:
    def __init__(self, model_dir):
        self.det = _session(os.path.join(model_dir, "face_tag_detector.onnx"))
        self.emb = _session(os.path.join(model_dir, "face_embedder.onnx"))
        self._ocr = None

    # ---- detection -------------------------------------------------------------------------
    def detect(self, rgb, conf=FACE_CONF):
        h, w = rgb.shape[:2]
        s = IMGSZ / max(h, w)
        nh, nw = round(h * s), round(w * s)
        canvas = np.full((IMGSZ, IMGSZ, 3), 114, np.uint8)
        top, left = (IMGSZ - nh) // 2, (IMGSZ - nw) // 2
        canvas[top:top + nh, left:left + nw] = cv2.resize(rgb, (nw, nh))
        x = (canvas.astype(np.float32) / 255).transpose(2, 0, 1)[None]
        out = self.det.run(None, {self.det.get_inputs()[0].name: x})[0][0]   # (4 + 2, 8400)
        dets = []
        for cls in (FACE, EAR_TAG):
            sc = out[4 + cls]
            keep = sc >= conf
            if not keep.any():
                continue
            b, s_ = out[:4, keep].T, sc[keep]
            xywh = np.stack([b[:, 0] - b[:, 2] / 2, b[:, 1] - b[:, 3] / 2, b[:, 2], b[:, 3]], 1)
            for i in np.array(cv2.dnn.NMSBoxes(xywh.tolist(), s_.tolist(), conf, IOU)).reshape(-1):
                x0, y0, bw, bh = xywh[i]
                box = (int(np.clip((x0 - left) / s, 0, w)), int(np.clip((y0 - top) / s, 0, h)),
                       int(np.clip((x0 + bw - left) / s, 0, w)), int(np.clip((y0 + bh - top) / s, 0, h)))
                dets.append((cls, float(s_[i]), box))
        return sorted(dets, key=lambda d: -d[1])

    @staticmethod
    def _crop(rgb, box, pad):
        h, w = rgb.shape[:2]
        x0, y0, x1, y1 = box
        px, py = (x1 - x0) * pad, (y1 - y0) * pad
        return rgb[max(0, int(y0 - py)):min(h, int(y1 + py)), max(0, int(x0 - px)):min(w, int(x1 + px))]

    # ---- embedding (timm DINOv2 transform: shorter side 224 bicubic, centre-crop 224, ImageNet norm) ----
    @staticmethod
    def _prep(crop):
        im = Image.fromarray(crop)
        w, h = im.size
        size = (224, int(224 * h / w)) if w <= h else (int(224 * w / h), 224)
        im = im.resize(size, Image.BICUBIC)
        l, t = (im.width - 224) // 2, (im.height - 224) // 2
        a = np.asarray(im.crop((l, t, l + 224, t + 224)), np.float32) / 255
        return ((a - MEAN) / STD).transpose(2, 0, 1)

    def embed(self, crops):
        x = np.stack([self._prep(c) for c in crops]).astype(np.float32)
        return self.emb.run(None, {self.emb.get_inputs()[0].name: x})[0]

    # ---- ear-tag OCR (RapidOCR, ~3 s per crop on CPU) -------------------------------------------
    def read_tag(self, crop):
        if self._ocr is None:
            from rapidocr_onnxruntime import RapidOCR
            self._ocr = RapidOCR()
        h, w = crop.shape[:2]
        sc = max(1.0, 96 / min(w, h))
        best = None
        for rot in (0, 90, 270, 180):
            im = Image.fromarray(crop).rotate(rot, expand=True)
            im = im.resize((int(im.width * sc), int(im.height * sc)), Image.LANCZOS)
            padded = Image.new("RGB", (im.width + 24, im.height + 24), (255, 255, 255))
            padded.paste(im, (12, 12))
            res, _ = self._ocr(np.asarray(padded)[:, :, ::-1])
            for _, text, conf in res or []:
                digits = re.sub(r"\D", "", text)
                if TAG_MIN_DIGITS <= len(digits) <= TAG_MAX_DIGITS and float(conf) >= TAG_MIN_CONF \
                        and (best is None or float(conf) > best["conf"]):
                    best = {"number": digits, "conf": round(float(conf), 3)}
        return best

    # ---- one frame ---------------------------------------------------------------------------------
    def predict(self, rgb, read_tags=False):
        dets = self.detect(rgb)
        tags = [d for d in dets if d[0] == EAR_TAG]
        faces, crops, slots, ocr_left = [], [], [], TAG_MAX_READS
        for _, c, box in [d for d in dets if d[0] == FACE]:
            crop = self._crop(rgb, box, FACE_PAD)
            item = {"box": list(box), "conf": round(c, 3), "usable": False, "reason": "", "tags": []}
            if crop.size == 0 or min(crop.shape[:2]) < MIN_SIDE:
                item["reason"] = "too_small"
            elif sharpness(cv2.cvtColor(crop, cv2.COLOR_RGB2GRAY)) < MIN_SHARP:
                item["reason"] = "blurry"
            else:
                crops.append(crop); slots.append(item)
            fx0, fy0, fx1, fy1 = box
            mx, my = (fx1 - fx0) * TAG_NEAR, (fy1 - fy0) * TAG_NEAR
            for _, tc, tb in tags:                      # tags belonging to this face
                cx, cy = (tb[0] + tb[2]) / 2, (tb[1] + tb[3]) / 2
                if fx0 - mx <= cx <= fx1 + mx and fy0 - my <= cy <= fy1 + my:
                    t = {"box": list(tb), "conf": round(tc, 3)}
                    if read_tags and ocr_left > 0:
                        tcrop = self._crop(rgb, tb, TAG_PAD)
                        if tcrop.size:
                            t["read"] = self.read_tag(tcrop); ocr_left -= 1
                    item["tags"].append(t)
            faces.append(item)
        if crops:
            for item, e in zip(slots, self.embed(crops)):
                item["usable"] = True
                item["embedding"] = [round(float(v), 5) for v in e]
        return {"faces": faces, "tags_in_frame": len(tags)}
