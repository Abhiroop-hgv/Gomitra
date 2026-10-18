import time, cv2
import pose_estimation as pe
img = cv2.imread("warmup.jpg")
t = time.time()
poses = pe.SuperAnimalBackend().estimate_frames([img, img])
print("WARMUP OK" if poses and poses[0] else "WARMUP: no keypoints", len(poses), "frames,", len(poses[0]) if poses else 0, "keypoints,", round(time.time() - t, 1), "s")
print({k: [round(v) for v in p[:2]] for k, p in list(poses[0].items())[:6]})
