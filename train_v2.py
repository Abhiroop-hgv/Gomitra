"""Retrain the cattle skin classifier on BOTH Kaggle datasets with 3 classes:
normal / lumpy / fmd (foot-and-mouth as a hard negative).

Near-duplicate images (e.g. Roboflow augmented copies) are grouped by perceptual hash and
each group goes to exactly one of train/val/test, so the test score is not inflated.
Kaggle notebook: attach "Lumpy Skin Images Dataset" and "Cattle diseases datasets".
"""
import os, glob, random
import numpy as np
import torch, torch.nn as nn
from PIL import Image
from torch.utils.data import Dataset, DataLoader
from torchvision import models, transforms
from sklearn.model_selection import StratifiedGroupKFold
from sklearn.metrics import classification_report, confusion_matrix

SEED, EPOCHS, BATCH, LR = 42, 12, 32, 1e-3
CLASSES = ["normal", "lumpy", "fmd"]
random.seed(SEED); np.random.seed(SEED); torch.manual_seed(SEED)
device = "cuda" if torch.cuda.is_available() else "cpu"
print("device:", device)

def label_of(p):
    name = os.path.basename(p).lower()
    folder = os.path.basename(os.path.dirname(p)).lower()
    if "foot" in folder or ("foot" in name and "mouth" in name):
        return 2
    if "lumpy" in folder:
        return 1
    if "normal" in folder or "healthy" in folder:
        return 0
    return None

def dhash_bits(im):
    g = np.asarray(im.convert("L").resize((9, 8), Image.LANCZOS), dtype=np.int16)
    return np.packbits((g[:, 1:] > g[:, :-1]).flatten())

paths, labels, hashes = [], [], []
for p in sorted(glob.glob("/kaggle/input/**/*.*", recursive=True)):
    if not p.lower().endswith((".png", ".jpg", ".jpeg")):
        continue
    y = label_of(p)
    if y is None:
        continue
    try:
        im = Image.open(p).convert("RGB")
        hashes.append(dhash_bits(im))
    except Exception:
        continue
    paths.append(p); labels.append(y)
labels = np.array(labels)
print("images:", len(paths), "| normal", int((labels == 0).sum()), "lumpy", int((labels == 1).sum()),
      "fmd", int((labels == 2).sum()))
assert len(set(labels.tolist())) == 3, "Need all 3 classes - check folder names"

# --- group near-duplicates (dHash distance <= 6) with union-find
H = np.stack(hashes)
POP = np.array([bin(i).count("1") for i in range(256)], dtype=np.uint8)
parent = list(range(len(paths)))
def find(a):
    while parent[a] != a:
        parent[a] = parent[parent[a]]; a = parent[a]
    return a
for i in range(len(paths) - 1):
    d = POP[H[i + 1:] ^ H[i]].sum(1)
    for j in np.nonzero(d <= 6)[0]:
        ra, rb = find(i), find(i + 1 + int(j))
        if ra != rb:
            parent[ra] = rb
groups = np.array([find(i) for i in range(len(paths))])
sizes = np.bincount(np.unique(groups, return_inverse=True)[1])
print("duplicate groups:", len(sizes), "| largest group:", int(sizes.max()))

sgkf = StratifiedGroupKFold(n_splits=7, shuffle=True, random_state=SEED)
folds = [te for _, te in sgkf.split(paths, labels, groups)]
test_idx, val_idx, train_idx = folds[0], folds[1], np.concatenate(folds[2:])
P = np.array(paths)
split = lambda idx: (P[idx].tolist(), labels[idx].tolist())
(tr_p, tr_y), (va_p, va_y), (te_p, te_y) = split(train_idx), split(val_idx), split(test_idx)
print("split sizes train/val/test:", len(tr_p), len(va_p), len(te_p))

norm = transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225])
train_tf = transforms.Compose([
    transforms.Resize((224, 224)),
    transforms.RandomHorizontalFlip(),
    transforms.RandomRotation(15),
    transforms.ColorJitter(0.3, 0.3, 0.2),
    transforms.RandomApply([transforms.GaussianBlur(5, (0.1, 2.0))], p=0.3),
    transforms.ToTensor(), norm,
])
eval_tf = transforms.Compose([transforms.Resize((224, 224)), transforms.ToTensor(), norm])

class DS(Dataset):
    def __init__(self, p, y, tf): self.p, self.y, self.tf = p, y, tf
    def __len__(self): return len(self.p)
    def __getitem__(self, i):
        return self.tf(Image.open(self.p[i]).convert("RGB")), self.y[i]

mk = lambda p, y, tf, sh: DataLoader(DS(p, y, tf), batch_size=BATCH, shuffle=sh, num_workers=2)
train_dl, val_dl, test_dl = mk(tr_p, tr_y, train_tf, True), mk(va_p, va_y, eval_tf, False), mk(te_p, te_y, eval_tf, False)

model = models.efficientnet_b0(weights=models.EfficientNet_B0_Weights.IMAGENET1K_V1)
model.classifier[1] = nn.Linear(model.classifier[1].in_features, len(CLASSES))
model.to(device)

cnt = np.bincount(tr_y, minlength=3)
w = torch.tensor(len(tr_y) / (3 * cnt), dtype=torch.float32).to(device)
crit = nn.CrossEntropyLoss(weight=w)
opt = torch.optim.AdamW(model.parameters(), lr=LR * 0.1, weight_decay=1e-4)
sched = torch.optim.lr_scheduler.CosineAnnealingLR(opt, EPOCHS)

def run(dl, train):
    model.train(train); tot, correct, loss_sum, preds, ys = 0, 0, 0.0, [], []
    with torch.set_grad_enabled(train):
        for x, y in dl:
            x, y = x.to(device), y.to(device)
            out = model(x); loss = crit(out, y)
            if train:
                opt.zero_grad(); loss.backward(); opt.step()
            loss_sum += loss.item() * len(y); tot += len(y)
            p = out.argmax(1); correct += (p == y).sum().item()
            preds += p.cpu().tolist(); ys += y.cpu().tolist()
    return loss_sum / tot, correct / tot, preds, ys

best, best_acc = None, 0
for ep in range(EPOCHS):
    tl, ta, _, _ = run(train_dl, True)
    vl, va, _, _ = run(val_dl, False)
    sched.step()
    print(f"epoch {ep+1:2d} | train loss {tl:.3f} acc {ta:.3f} | val loss {vl:.3f} acc {va:.3f}")
    if va >= best_acc:
        best_acc, best = va, {k: v.cpu().clone() for k, v in model.state_dict().items()}

model.load_state_dict(best)
_, acc, preds, ys = run(test_dl, False)
print("\n=== TEST SET (no duplicates of training images) ===")
print("3-class accuracy:", round(acc, 3))
print(confusion_matrix(ys, preds))
print(classification_report(ys, preds, target_names=CLASSES, digits=3))
ys_a, pr_a = np.array(ys), np.array(preds)
print("lumpy-vs-everything-else accuracy:", round(float(((ys_a == 1) == (pr_a == 1)).mean()), 3))

torch.save({"state_dict": best, "classes": CLASSES}, "/kaggle/working/lsd_v2_3class.pt")
print("saved /kaggle/working/lsd_v2_3class.pt")
