#!/usr/bin/env python3
"""GoMitra Raspberry Pi uploader. Captures a photo and a short sound clip on a schedule and uploads them.
No AI runs on the Pi: the cloud router looks at what arrived and sends it to the right model.

  python3 gomitra_pi.py --url https://YOUR-SERVICE.run.app --key DEVICE_KEY --camera "North field camera"
  python3 gomitra_pi.py --url ... --key ... --send some_photo.jpg      # upload one existing file and print the reply (testing)

The key can also come from the GOMITRA_KEY environment variable and the address from GOMITRA_URL.
If the network is down, files wait in a spool folder and are sent later (oldest are dropped past 50 files).
"""
import argparse
import base64
import glob
import json
import logging
import os
import shutil
import subprocess
import sys
import tempfile
import time

import requests

log = logging.getLogger("gomitra-pi")


def capture_photo(path):
    """Pi camera first (rpicam-still, then libcamera-still), then a USB camera through OpenCV."""
    for tool in ("rpicam-still", "libcamera-still"):
        if shutil.which(tool):
            r = subprocess.run([tool, "-n", "-t", "800", "--width", "1280", "--height", "960", "-o", path],
                               capture_output=True, timeout=30)
            if r.returncode == 0 and os.path.getsize(path) > 0:
                return True
    try:
        import cv2
        cap = cv2.VideoCapture(0)
        ok, frame = cap.read()
        cap.release()
        if ok:
            cv2.imwrite(path, frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
            return True
    except Exception as e:                       # OpenCV missing or no camera
        log.warning("USB camera not usable: %s", e)
    return False


def capture_clip(path, seconds):
    """A short MP4 so the cloud's frame agent can pick the best frames itself. Pi camera first (rpicam-vid), then a USB
    camera through OpenCV (about 5 frames a second)."""
    for tool in ("rpicam-vid", "libcamera-vid"):
        if shutil.which(tool):
            r = subprocess.run([tool, "-n", "-t", str(seconds * 1000), "--width", "1280", "--height", "720", "--codec", "libav",
                                "--libav-format", "mp4", "-o", path], capture_output=True, timeout=seconds + 30)
            if r.returncode == 0 and os.path.exists(path) and os.path.getsize(path) > 1000:
                return True
    try:
        import cv2
        cap = cv2.VideoCapture(0)
        ok, frame = cap.read()
        if not ok:
            cap.release()
            return False
        h, w = frame.shape[:2]
        vw = cv2.VideoWriter(path, cv2.VideoWriter_fourcc(*"mp4v"), 5, (w, h))
        end = time.time() + seconds
        while time.time() < end:
            ok, frame = cap.read()
            if ok:
                vw.write(frame)
            time.sleep(0.2)
        vw.release()
        cap.release()
        return os.path.getsize(path) > 1000
    except Exception as e:
        log.warning("clip capture failed: %s", e)
        return False


def capture_sound(path, seconds):
    """Records mono 16-bit WAV with arecord (ALSA); the cloud resamples it."""
    if not shutil.which("arecord"):
        return False
    r = subprocess.run(["arecord", "-q", "-d", str(seconds), "-f", "S16_LE", "-r", "22050", "-c", "1", path],
                       capture_output=True, timeout=seconds + 15)
    return r.returncode == 0 and os.path.exists(path) and os.path.getsize(path) > 1000


def upload(url, key, camera, path):
    """-> reply dict. Raises requests.RequestException on network errors; the pose step can take about 2 minutes."""
    with open(path, "rb") as f:
        body = {"file": base64.b64encode(f.read()).decode(), "camera": camera}
    r = requests.post(url.rstrip("/") + "/api/ingest", json=body, headers={"x-device-key": key}, timeout=200)
    if r.status_code == 403:
        sys.exit("The cloud rejected the device key (403). Check --key.")
    if r.status_code in (413, 415, 422):          # this file will never be accepted: do not keep retrying it
        log.warning("rejected %s (%s): %s", os.path.basename(path), r.status_code, r.text[:200])
        return {"rejected": True}
    r.raise_for_status()
    return r.json()


def spool(path, spool_dir):
    os.makedirs(spool_dir, exist_ok=True)
    shutil.copy(path, os.path.join(spool_dir, f"{int(time.time() * 1000)}_{os.path.basename(path)}"))
    old = sorted(glob.glob(os.path.join(spool_dir, "*")))
    for p in old[:-50]:
        os.remove(p)


def flush(url, key, camera, spool_dir):
    for p in sorted(glob.glob(os.path.join(spool_dir, "*")))[:10]:
        try:
            upload(url, key, camera, p)
            os.remove(p)
        except requests.RequestException:
            return                                 # still offline; try again next round


def send(url, key, camera, path, spool_dir):
    try:
        r = upload(url, key, camera, path)
        log.info("sent %s -> %s", os.path.basename(path), r.get("summary") or r)
        return r
    except requests.RequestException as e:
        log.warning("upload failed (%s); keeping %s for later", type(e).__name__, os.path.basename(path))
        spool(path, spool_dir)


def replay(a):
    """Camera stand-in for demos: take frames from a recorded video (or a folder of photos) and upload them one by one,
    as if the camera had captured them. Everything after the upload is the real cloud pipeline."""
    work = tempfile.mkdtemp(prefix="gomitra-replay-")
    if os.path.isdir(a.replay):
        items = sorted(p for p in glob.glob(os.path.join(a.replay, "*")) if p.lower().endswith((".jpg", ".jpeg", ".png")))
        grab = lambda: iter(items)
    else:
        import cv2

        def grab():
            cap = cv2.VideoCapture(a.replay)
            if not cap.isOpened():
                sys.exit(f"Cannot open {a.replay}")
            fps = cap.get(cv2.CAP_PROP_FPS) or 25
            total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            step = max(1, int(fps * a.replay_step))
            for i in range(0, total, step):
                cap.set(cv2.CAP_PROP_POS_FRAMES, i)
                ok, frame = cap.read()
                if ok:
                    p = os.path.join(work, f"frame_{i}.jpg")
                    cv2.imwrite(p, frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
                    yield p
            cap.release()
    n = 0
    while True:
        for p in grab():
            n += 1
            log.info("replay frame %d: %s", n, os.path.basename(p))
            send(a.url, a.key, a.camera, p, a.spool)
            time.sleep(a.replay_gap)
        if not a.loop:
            break
    log.info("replay finished (%d frames)", n)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--url", default=os.getenv("GOMITRA_URL"))
    ap.add_argument("--key", default=os.getenv("GOMITRA_KEY"))
    ap.add_argument("--camera", default=os.getenv("GOMITRA_CAMERA", "North field camera"))
    ap.add_argument("--photo-every", type=int, default=60, help="seconds between photos (0 = never)")
    ap.add_argument("--video-every", type=int, default=0, help="seconds between short video clips (0 = never). Best option: the cloud agent picks the good frames")
    ap.add_argument("--video-seconds", type=int, default=5)
    ap.add_argument("--sound-every", type=int, default=120, help="seconds between sound clips (0 = never)")
    ap.add_argument("--sound-seconds", type=int, default=10)
    ap.add_argument("--spool", default=os.path.join(tempfile.gettempdir(), "gomitra-spool"))
    ap.add_argument("--send", metavar="FILE", help="upload this one file, print the reply, and exit")
    ap.add_argument("--replay", metavar="VIDEO_OR_FOLDER", help="demo mode: upload frames of a recorded video (or the photos in a folder) as if a camera took them")
    ap.add_argument("--replay-step", type=float, default=5.0, help="seconds of video between uploaded frames")
    ap.add_argument("--replay-gap", type=float, default=4.0, help="real seconds to wait between uploads")
    ap.add_argument("--loop", action="store_true", help="repeat the replay until stopped")
    a = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    if not a.url or not a.key:
        sys.exit("Need --url and --key (or GOMITRA_URL and GOMITRA_KEY).")
    if a.replay:
        replay(a)
        return
    if a.send:
        r = send(a.url, a.key, a.camera, a.send, a.spool)
        print(json.dumps(r, indent=2))
        return
    work = tempfile.mkdtemp(prefix="gomitra-")
    due = {"photo": 0.0, "video": 0.0, "sound": 0.0}
    log.info("running: camera=%r photo every %ss, sound every %ss", a.camera, a.photo_every, a.sound_every)
    while True:
        try:
            now = time.time()
            if a.photo_every and now >= due["photo"]:
                due["photo"] = now + a.photo_every
                p = os.path.join(work, "frame.jpg")
                if capture_photo(p):
                    send(a.url, a.key, a.camera, p, a.spool)
                else:
                    log.warning("no camera found")
            if a.video_every and time.time() >= due["video"]:
                due["video"] = time.time() + a.video_every
                p = os.path.join(work, "clip.mp4")
                if capture_clip(p, a.video_seconds):
                    send(a.url, a.key, a.camera, p, a.spool)
                else:
                    log.warning("no camera found for a video clip")
            if a.sound_every and time.time() >= due["sound"]:
                due["sound"] = time.time() + a.sound_every
                p = os.path.join(work, "clip.wav")
                if capture_sound(p, a.sound_seconds):
                    send(a.url, a.key, a.camera, p, a.spool)
                else:
                    log.warning("no microphone found (is arecord installed?)")
            flush(a.url, a.key, a.camera, a.spool)
        except KeyboardInterrupt:
            break
        except Exception:                          # never let one bad round stop the loop
            log.exception("round failed")
        time.sleep(2)


if __name__ == "__main__":
    main()
