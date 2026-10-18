"""Evaluate the LSD classifier on an external dataset and check train/test overlap.

usage: python eval_external.py MODEL.pt DATA_ROOT TRAIN_ZIP
  DATA_ROOT has subfolders: healthy/ lumpy/ (foot-and-mouth/ optional)
  TRAIN_ZIP is the Lumpy Skin Images Dataset zip the model was trained on
"""
import sys, os, io, zipfile
import numpy as np
import torch, torch.nn as nn
from PIL import Image
from torchvision import models, transforms

model_path, root, train_zip = sys.argv[1:4]
EXT = (".png", ".jpg", ".jpeg", ".webp")

ckpt = torch.load(model_path, map_location="cpu")
classes = ckpt["classes"]; LUMPY = classes.index("lumpy")
model = models.efficientnet_b0()
model.classifier[1] = nn.Linear(model.classifier[1].in_features, len(classes))
model.load_state_dict(ckpt["state_dict"]); model.eval()
tf = transforms.Compose([transforms.Resize((224, 224)), transforms.ToTensor(),
                         transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225])])

def dhash(img, n=8):
    g = np.asarray(img.convert("L").resize((n + 1, n), Image.LANCZOS), dtype=np.int16)
    return (g[:, 1:] > g[:, :-1]).flatten()

def files_in(sub):
    d = os.path.join(root, "Cows datasets" if not os.path.isdir(os.path.join(root, sub)) else "", sub)
    return sorted(os.path.join(d, f) for f in os.listdir(d) if f.lower().endswith(EXT)) if os.path.isdir(d) else []

# --- hashes of the training images (read straight from the zip)
train_h = []
with zipfile.ZipFile(train_zip) as z:
    for name in z.namelist():
        if name.lower().endswith(EXT):
            try: train_h.append(dhash(Image.open(io.BytesIO(z.read(name)))))
            except Exception: pass
train_h = np.array(train_h)
print(f"training images hashed: {len(train_h)}")

def predict_all(paths):
    probs, hashes, ok = [], [], []
    batch, bp = [], []
    def flush():
        if batch:
            with torch.no_grad():
                p = torch.softmax(model(torch.stack(batch)), 1)[:, LUMPY].numpy()
            probs.extend(p.tolist())
    for f in paths:
        try:
            im = Image.open(f).convert("RGB")
        except Exception:
            continue
        hashes.append(dhash(im)); ok.append(f); batch.append(tf(im))
        if len(batch) == 32:
            flush(); batch = []
    flush()
    return np.array(probs), np.array(hashes), ok

def min_dist(h):
    return int((train_h != h).sum(1).min())

res = {}
for sub in ("healthy", "lumpy", "foot-and-mouth"):
    paths = files_in(sub)
    if not paths: continue
    p, h, ok = predict_all(paths)
    d = np.array([min_dist(x) for x in h])
    res[sub] = (p, d)
    print(f"{sub}: {len(ok)} images scored")

def report(title, mask_fn):
    print(f"\n=== {title} ===")
    tn = fp = fn = tp = 0
    for sub, label in (("healthy", 0), ("lumpy", 1)):
        p, d = res[sub]; m = mask_fn(d); pred = p[m] > 0.5
        if label == 0: tn += int((~pred).sum()); fp += int(pred.sum())
        else: fn += int((~pred).sum()); tp += int(pred.sum())
    n = tn + fp + fn + tp
    print(f"images: {n} (healthy {tn+fp}, lumpy {tp+fn})")
    print(f"confusion  [[TN {tn}, FP {fp}], [FN {fn}, TP {tp}]]")
    print(f"accuracy {(tn+tp)/n:.3f} | lumpy recall {tp/max(tp+fn,1):.3f} | lumpy precision {tp/max(tp+fp,1):.3f} | healthy recall {tn/max(tn+fp,1):.3f}")

THRESH = 6
dups = {s: int((res[s][1] <= THRESH).sum()) for s in ("healthy", "lumpy")}
print(f"\nnear-duplicates of training images (dHash distance <= {THRESH}): {dups}")
report("ALL external images", lambda d: np.ones_like(d, dtype=bool))
report(f"ONLY images NOT similar to training (distance > {THRESH})", lambda d: d > THRESH)

if "foot-and-mouth" in res:
    p, d = res["foot-and-mouth"]
    print(f"\nfoot-and-mouth (not a trained class): {int((p > 0.5).sum())}/{len(p)} predicted lumpy "
          f"({(p > 0.5).mean():.1%})")
