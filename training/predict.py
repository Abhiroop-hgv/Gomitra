"""Run the trained LSD classifier on image files or folders.

usage: python predict.py MODEL.pt IMAGE_OR_FOLDER [IMAGE_OR_FOLDER ...]
"""
import sys, os
import torch, torch.nn as nn
from PIL import Image
from torchvision import models, transforms

model_path, targets = sys.argv[1], sys.argv[2:]

ckpt = torch.load(model_path, map_location="cpu")
classes = ckpt["classes"]
model = models.efficientnet_b0()
model.classifier[1] = nn.Linear(model.classifier[1].in_features, len(classes))
model.load_state_dict(ckpt["state_dict"])
model.eval()

tf = transforms.Compose([
    transforms.Resize((224, 224)), transforms.ToTensor(),
    transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
])

files = []
for t in targets:
    if os.path.isdir(t):
        files += [os.path.join(t, f) for f in sorted(os.listdir(t))
                  if f.lower().endswith((".png", ".jpg", ".jpeg", ".webp"))]
    else:
        files.append(t)

with torch.no_grad():
    for f in files:
        x = tf(Image.open(f).convert("RGB")).unsqueeze(0)
        p = torch.softmax(model(x), 1)[0]
        print(f"{os.path.basename(f):40s} -> {classes[int(p.argmax())]:7s} "
              f"(lumpy {p[classes.index('lumpy')]:.2f}, normal {p[classes.index('normal')]:.2f})")
