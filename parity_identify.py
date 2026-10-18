"""Compare ONNX port (serving/identify.py) with the repo's PyTorch pipeline. python parity_identify.py PHOTO_ROOT N"""
import sys, glob, os, random
sys.path.insert(0, r"C:\Users\Admin\cattle_repo_clone\Cattle-detection"); sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "serving"))
import numpy as np, cv2
from PIL import Image
from cattle_id.config import Config
from cattle_id.detector import FaceTagDetector
from cattle_id.embedder import Embedder
from identify import Identify

root, N = sys.argv[1], int(sys.argv[2])
repo = r"C:\Users\Admin\cattle_repo_clone\Cattle-detection"
cfg = Config(face_detector_weights=os.path.join(repo, "checkpoints", "face_tag_detector.pt"), checkpoint=os.path.join(repo, "checkpoints", "face_embedder.pt"))
det, emb = FaceTagDetector(cfg), Embedder(cfg, device="cpu")
mine = Identify(os.path.join(os.path.dirname(os.path.abspath(__file__)), "serving", "models"))
random.seed(3); files = []
for f in os.listdir(root): files += random.sample(sorted(glob.glob(os.path.join(root, f, "*.*"))), min(N, 400))
def iou(a, b):
    x0, y0, x1, y1 = max(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), min(a[3], b[3]); i = max(0, x1 - x0) * max(0, y1 - y0)
    return i / ((a[2]-a[0])*(a[3]-a[1]) + (b[2]-b[0])*(b[3]-b[1]) - i + 1e-9)
n_img = n_ref = n_mine = n_match = 0; cos = []; tag_ref = tag_mine = 0
for p in files:
    img = Image.open(p).convert("RGB"); rgb = np.asarray(img)
    ref_f = det.faces(img); ref_t = [d for d in det.detect(img) if d.label == "ear_tag"]
    m = mine.predict(rgb)
    n_img += 1; n_ref += len(ref_f); n_mine += len(m["faces"]); tag_ref += len(ref_t); tag_mine += m["tags_in_frame"]
    for crop, d in ref_f:
        best = max(m["faces"], key=lambda f: iou(f["box"], d.box), default=None)
        if best and iou(best["box"], d.box) > 0.8:
            n_match += 1
            if best["usable"]:
                cos.append(float(np.dot(emb.embed([crop])[0], best["embedding"])))
print(f"images {n_img}: faces repo {n_ref} | mine {n_mine} | matched (IoU>0.8) {n_match}; ear tags repo {tag_ref} | mine {tag_mine}")
if cos: print(f"embedding cosine mine-vs-repo on {len(cos)} matched usable faces: min {min(cos):.4f} mean {np.mean(cos):.4f}")
