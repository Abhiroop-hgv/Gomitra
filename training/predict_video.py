"""Detect cows in a video, track them, classify each crop (normal/lumpy/fmd), vote per cow.

usage: python predict_video.py MODEL.pt VIDEO.mp4 OUT.mp4 [frame_stride]
"""
import sys
from collections import defaultdict
import cv2, numpy as np
import torch, torch.nn as nn
from torchvision import models, transforms
from ultralytics import YOLO

model_path, video, out_path = sys.argv[1:4]
STRIDE = int(sys.argv[4]) if len(sys.argv) > 4 else 2
MIN_SIDE, MIN_SHARP, COW = 80, 20.0, 19  # px, laplacian variance, COCO 'cow' class id

ckpt = torch.load(model_path, map_location="cpu")
classes = ckpt["classes"]
clf = models.efficientnet_b0()
clf.classifier[1] = nn.Linear(clf.classifier[1].in_features, len(classes))
clf.load_state_dict(ckpt["state_dict"]); clf.eval()
tf = transforms.Compose([transforms.ToPILImage(), transforms.Resize((224, 224)), transforms.ToTensor(),
                         transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225])])
det = YOLO("yolo11n.pt")

cap = cv2.VideoCapture(video)
fps = cap.get(cv2.CAP_PROP_FPS) or 25
W, H = int(cap.get(3)), int(cap.get(4))
writer = cv2.VideoWriter(out_path, cv2.VideoWriter_fourcc(*"mp4v"), fps / STRIDE, (W, H))
COLORS = {"normal": (0, 200, 0), "lumpy": (0, 0, 255), "fmd": (0, 165, 255)}

probs = defaultdict(list)       # track id -> list of prob vectors
frames_with_cow = n = 0
while True:
    ok, frame = cap.read()
    if not ok:
        break
    n += 1
    if n % STRIDE:
        continue
    r = det.track(frame, persist=True, classes=[COW], conf=0.3, verbose=False, tracker="bytetrack.yaml")[0]
    if r.boxes is not None and len(r.boxes):
        frames_with_cow += 1
        ids = r.boxes.id.int().tolist() if r.boxes.id is not None else [-1] * len(r.boxes)
        for (x1, y1, x2, y2), tid in zip(r.boxes.xyxy.int().tolist(), ids):
            x1, y1, x2, y2 = max(x1, 0), max(y1, 0), min(x2, W), min(y2, H)
            crop = frame[y1:y2, x1:x2]
            label, color = "cow (crop too small/blurry)", (160, 160, 160)
            if min(crop.shape[:2]) >= MIN_SIDE and cv2.Laplacian(cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY), cv2.CV_64F).var() >= MIN_SHARP:
                with torch.no_grad():
                    p = torch.softmax(clf(tf(cv2.cvtColor(crop, cv2.COLOR_BGR2RGB)).unsqueeze(0)), 1)[0].numpy()
                probs[tid].append(p)
                avg = np.mean(probs[tid], 0); k = int(avg.argmax())
                label, color = f"#{tid} {classes[k]} {avg[k]:.0%} (n={len(probs[tid])})", COLORS[classes[k]]
            cv2.rectangle(frame, (x1, y1), (x2, y2), color, 3)
            cv2.putText(frame, label, (x1, max(y1 - 8, 20)), cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2)
    writer.write(frame)
cap.release(); writer.release()

print(f"\nframes read: {n} | processed every {STRIDE} | frames with a cow: {frames_with_cow}")
print("tracked cows (classified crops only), vote = mean probability:")
for tid, ps in sorted(probs.items(), key=lambda kv: -len(kv[1])):
    avg = np.mean(ps, 0)
    votes = np.bincount([int(p.argmax()) for p in ps], minlength=len(classes))
    print(f"  cow #{tid}: {len(ps):3d} crops -> {classes[int(avg.argmax())]:6s} "
          + " ".join(f"{c}={avg[i]:.2f}" for i, c in enumerate(classes))
          + " | frame votes " + " ".join(f"{c}={votes[i]}" for i, c in enumerate(classes)))
print("saved", out_path)
