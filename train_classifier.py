"""Fine-tune EfficientNet-B0 to classify lumpy skin disease vs normal cattle skin.

Written for a Kaggle notebook with the "Lumpy Skin Images Dataset" attached.
Outputs /kaggle/working/lsd_efficientnet_b0.pt and prints test metrics.
"""
import os, random, glob
import numpy as np
import torch, torch.nn as nn
from PIL import Image
from torch.utils.data import Dataset, DataLoader
from torchvision import models, transforms
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report, confusion_matrix

SEED, EPOCHS, BATCH, LR = 42, 10, 32, 1e-3
random.seed(SEED); np.random.seed(SEED); torch.manual_seed(SEED)
device = "cuda" if torch.cuda.is_available() else "cpu"
print("device:", device)

# --- label by the image's own parent folder name (not the whole path, which
# --- also contains the dataset name "lumpy-skin-images-dataset")
items = []
for p in glob.glob("/kaggle/input/**/*.*", recursive=True):
    if not p.lower().endswith((".png", ".jpg", ".jpeg")):
        continue
    folder = os.path.basename(os.path.dirname(p)).lower()
    if "lumpy" in folder:
        items.append((p, 1))
    elif "normal" in folder:
        items.append((p, 0))
paths = [p for p, _ in items]; labels = [y for _, y in items]
print(f"found {len(items)} images | lumpy={sum(labels)} normal={len(labels) - sum(labels)}")
assert len(set(labels)) == 2, "Need both classes - check folder names under /kaggle/input"

# 70/15/15 stratified split
tr_p, tmp_p, tr_y, tmp_y = train_test_split(paths, labels, test_size=0.30, stratify=labels, random_state=SEED)
va_p, te_p, va_y, te_y = train_test_split(tmp_p, tmp_y, test_size=0.50, stratify=tmp_y, random_state=SEED)

norm = transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225])
train_tf = transforms.Compose([
    transforms.Resize((224, 224)),
    transforms.RandomHorizontalFlip(),
    transforms.RandomRotation(15),
    transforms.ColorJitter(0.3, 0.3, 0.2),
    transforms.RandomApply([transforms.GaussianBlur(5, (0.1, 2.0))], p=0.3),  # CCTV-like blur
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
model.classifier[1] = nn.Linear(model.classifier[1].in_features, 2)
model.to(device)

# class weights: lumpy images are the minority
cnt = np.bincount(tr_y); w = torch.tensor(len(tr_y) / (2 * cnt), dtype=torch.float32).to(device)
crit = nn.CrossEntropyLoss(weight=w)
opt = torch.optim.AdamW(model.parameters(), lr=LR * 0.1, weight_decay=1e-4)
sched = torch.optim.lr_scheduler.CosineAnnealingLR(opt, EPOCHS)

def run(dl, train):
    model.train(train); tot, correct, loss_sum, preds, ys = 0, 0, 0.0, [], []
    with torch.set_grad_enabled(train):
        for x, y in dl:
            x, y = x.to(device), y.to(device)
            out = model(x); loss = crit(out, y)
            if train: opt.zero_grad(); loss.backward(); opt.step()
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
_, _, preds, ys = run(test_dl, False)
print("\n=== TEST SET (never seen during training) ===")
print(confusion_matrix(ys, preds))
print(classification_report(ys, preds, target_names=["normal", "lumpy"], digits=3))

torch.save({"state_dict": best, "classes": ["normal", "lumpy"]}, "/kaggle/working/lsd_efficientnet_b0.pt")
print("saved /kaggle/working/lsd_efficientnet_b0.pt")
