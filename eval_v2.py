"""Sanity-check the 3-class model on a folder tree: ROOT/<healthy|lumpy|foot-and-mouth>/*.jpg
NOTE: if the model was trained on these images, this is NOT an independent test.

usage: python eval_v2.py MODEL.pt ROOT
"""
import sys, os
import numpy as np
import torch, torch.nn as nn
from PIL import Image
from torchvision import models, transforms

model_path, root = sys.argv[1:3]
ckpt = torch.load(model_path, map_location="cpu")
classes = ckpt["classes"]
model = models.efficientnet_b0()
model.classifier[1] = nn.Linear(model.classifier[1].in_features, len(classes))
model.load_state_dict(ckpt["state_dict"]); model.eval()
print("classes:", classes)

tf = transforms.Compose([transforms.Resize((224, 224)), transforms.ToTensor(),
                         transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225])])
truth = {"healthy": "normal", "lumpy": "lumpy", "foot-and-mouth": "fmd"}
base = os.path.join(root, "Cows datasets")
conf = np.zeros((3, 3), dtype=int)

for folder, cls in truth.items():
    d = os.path.join(base, folder)
    files = sorted(f for f in os.listdir(d) if f.lower().endswith((".png", ".jpg", ".jpeg", ".webp")))
    batch = []
    def flush():
        global batch
        if batch:
            with torch.no_grad():
                for p in model(torch.stack(batch)).argmax(1).tolist():
                    conf[classes.index(cls), p] += 1
            batch = []
    for f in files:
        try:
            batch.append(tf(Image.open(os.path.join(d, f)).convert("RGB")))
        except Exception:
            continue
        if len(batch) == 32:
            flush()
    flush()
    print(f"scored {folder}", flush=True)

print("\nrows = true, cols = predicted", classes)
print(conf)
n = conf.sum(); print(f"\n3-class accuracy: {np.trace(conf)/n:.3f} on {n} images")
L = classes.index("lumpy"); F = classes.index("fmd"); N = classes.index("normal")
print(f"lumpy recall {conf[L, L]/conf[L].sum():.3f} | lumpy precision {conf[L, L]/conf[:, L].sum():.3f}")
print(f"fmd recall {conf[F, F]/conf[F].sum():.3f} | fmd predicted as lumpy: {conf[F, L]}/{conf[F].sum()}")
print(f"normal recall {conf[N, N]/conf[N].sum():.3f} | normal predicted as lumpy: {conf[N, L]}/{conf[N].sum()}")
