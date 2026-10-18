"""The checks end to end with the real models run in-process (needs ../serving/models; skipped without them).

Covers: skin screening on photos, cow recognition, sound clips with "check this cow first", and the Raspberry Pi route with the
frame agent. Gemini is unreachable in tests, so alert text comes from the fixed templates.
"""
import base64
import tempfile
from pathlib import Path

import cv2
import numpy as np
import pytest

from tests.conftest import SAMPLES, sample_b64

pytestmark = pytest.mark.models


def tiny_jpeg():
    return base64.b64encode(cv2.imencode(".jpg", np.full((40, 40, 3), 128, np.uint8))[1].tobytes()).decode()


# ---- skin screening
def test_a_healthy_photo_has_no_finding_and_the_cow_stays_healthy(client, admin):
    client.post("/api/demo/seed", headers=admin)
    r = client.post("/api/analyze", json={"image": sample_b64("normal_1.jpg"), "mode": "photo", "cow_id": "rani"}).json()
    x = r["results"][0]
    assert x["usable"] and x["finding"] is None and x["probs"]["normal"] > 0.9 and not x["alert"]
    assert client.get("/api/cows/rani").json()["signals"]["skin"] == "ok"


def test_a_lumpy_photo_raises_an_alert_on_the_chosen_cow(client, admin):
    client.post("/api/demo/seed", headers=admin)
    x = client.post("/api/analyze", json={"image": sample_b64("lumpy_1.jpg"), "mode": "photo", "cow_id": "gauri"}).json()["results"][0]
    assert x["finding"]["kind"] == "lumpy" and x["alert"] and set(x["message"]) == {"en", "hi", "te"}
    g = client.get("/api/cows/gauri").json()
    assert g["alert"] and g["kind"] == "lumpy" and g["short"]["en"] == "Lumps on skin"


def test_a_foot_and_mouth_photo_is_high_severity(client, admin):
    client.post("/api/demo/seed", headers=admin)
    x = client.post("/api/analyze", json={"image": sample_b64("fmd_1.jpg"), "mode": "photo", "cow_id": "ganga"}).json()["results"][0]
    assert x["finding"]["kind"] == "fmd" and x["finding"]["severity"] == "high"


def test_a_photo_that_is_too_small_is_refused_without_an_alert(client, admin):
    client.post("/api/demo/seed", headers=admin)
    x = client.post("/api/analyze", json={"image": tiny_jpeg(), "mode": "photo", "cow_id": "rani"}).json()["results"][0]
    assert x["usable"] is False and x["reason"] == "too_small" and x["finding"] is None and not x["alert"]


def test_an_unregistered_cow_gets_a_message_but_nothing_is_stored(client):
    r = client.post("/api/analyze", json={"image": sample_b64("lumpy_1.jpg"), "mode": "photo"}).json()["results"][0]
    assert r["cow"] is None and r["message"]["en"]["title"] and client.get("/api/cows").json() == []


def test_the_result_names_the_service_that_did_each_step(client):
    r = client.post("/api/analyze", json={"image": sample_b64("normal_1.jpg"), "mode": "photo"}).json()
    assert r["trace"][0]["service"] == "Local models" and r["trace"][0]["ms"] > 0 and "lumpy_photo" in r["trace"][0]["detail"]


def test_a_cow_is_recognised_by_her_face_after_registration(client):
    photos = {k: "data:image/jpeg;base64," + sample_b64("normal_1.jpg") for k in ("front", "left", "right", "back")}
    reg = client.post("/api/cows", json={"name": "Face Test", "tag": "0777", "photos": photos}).json()
    assert reg["faces_found"] >= 1
    x = client.post("/api/analyze", json={"image": sample_b64("normal_1.jpg"), "mode": "photo"}).json()["results"][0]
    assert x["cow"]["id"] == "face-test-0777" and x["match"]["method"] == "face" and x["match"]["score"] > 0.9


# ---- sound
def test_a_distress_clip_alerts_at_once_in_demo_mode_and_names_the_cow_to_check_first(client, seeded):
    d = client.post("/api/audio", json={"audio": sample_b64("sound_distress.wav"), "camera": "North field camera", "immediate": True}).json()
    assert d["finding"] and d["alert"]["kind"] == "distress" and d["alert"]["stands_out"]
    assert "Tulasi" in d["alert"]["check_first"]["en"] and "Tulasi" in d["alert"]["check_first"]["te"]
    assert d["alert"]["msg"]["hi"]["advice"].endswith(d["alert"]["check_first"]["hi"])
    assert d["trace"][0]["service"] == "Local models"


def test_normally_one_distress_clip_is_not_enough_but_two_are(client):
    clip = {"audio": sample_b64("sound_distress.wav"), "camera": "Camera 9"}
    first = client.post("/api/audio", json=clip).json()
    assert first["finding"] and first["alert"] is None and "two matching clips" in first["note"]
    assert client.post("/api/audio", json=clip).json()["alert"]["kind"] == "distress"


def test_a_calm_clip_gives_no_distress_and_counts_as_eating_sound(client):
    d = client.post("/api/audio", json={"audio": sample_b64("sound_calm.wav"), "camera": "Camera 9", "immediate": True}).json()
    assert d["finding"] is None and d["alert"] is None and d["audio"]["bite_chew"]["label"] in ("chew", "bite", "chew-bite")
    assert client.get("/api/feeding", params={"camera": "Camera 9"}).json()["clips"] == 1


# ---- walking and resting (the pose service is not configured in tests: no pose, and Gemini is unreachable, so no score)
def test_a_walking_check_without_the_pose_service_says_no_score_instead_of_guessing(client):
    r = client.post("/api/posture", json={"images": [sample_b64("walk_lame.jpg")]}).json()
    assert r["pose_used"] is False and r["gait"]["score"] is None and r["alert"] is False


# ---- the Raspberry Pi route and the frame agent
def letterbox(img, W=640, H=480):
    s = min(W / img.shape[1], H / img.shape[0])
    im = cv2.resize(img, (round(img.shape[1] * s), round(img.shape[0] * s)))
    out = np.zeros((H, W, 3), np.uint8)
    y, x = (H - im.shape[0]) // 2, (W - im.shape[1]) // 2
    out[y:y + im.shape[0], x:x + im.shape[1]] = im
    return out


@pytest.fixture
def mixed_clip():
    """A short video: blurred, dark and close-up frames mixed with three real cow frames, 3 frames a second."""
    rd = lambda n: letterbox(cv2.imread(str(SAMPLES / n)))
    good = [rd("walk_lame.jpg"), rd("walk_sahiwal.jpg"), rd("walk_tharparkar.jpg")]
    seq = ([cv2.GaussianBlur(good[0], (0, 0), 25)] * 3 + [(good[0] * 0.05).astype(np.uint8)] * 3 + [rd("lumpy_1.jpg")] * 3
           + [g for g in good for _ in range(3)])
    path = Path(tempfile.mkdtemp()) / "clip.mp4"
    vw = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), 3, (640, 480))
    for f in seq:
        vw.write(f)
    vw.release()
    return base64.b64encode(path.read_bytes()).decode()


def test_a_close_up_with_no_whole_cow_reaches_no_model(client, device):
    j = client.post("/api/ingest", json={"file": sample_b64("lumpy_1.jpg"), "camera": "Cam"}, headers=device).json()
    assert j["routed"] is False and "skin model" not in j["steps"] and "Nothing was sent" in j["decisions"][-1]


def test_a_clear_side_on_cow_goes_to_the_skin_model(client, device):
    j = client.post("/api/ingest", json={"file": sample_b64("walk_tharparkar.jpg"), "camera": "Cam"}, headers=device).json()
    assert j["routed"] and "skin model" in j["steps"] and any("skin model" in d for d in j["decisions"])


def test_a_sound_clip_goes_to_the_sound_models(client, device):
    j = client.post("/api/ingest", json={"file": sample_b64("sound_distress.wav"), "camera": "Cam"}, headers=device).json()
    assert j["kind"] == "audio" and "sound models" in j["steps"] and j["distress"] is True


def test_a_video_is_cleaned_up_by_the_agent_before_any_model_sees_it(client, device, mixed_clip):
    j = client.post("/api/ingest", json={"file": mixed_clip, "camera": "Cam"}, headers=device).json()
    first = j["decisions"][0]
    assert j["kind"] == "video" and j["routed"]
    assert "blurred" in first and "too dark" in first and "near-duplicate" in first
    assert any("side-on" in d and "pose model" in d for d in j["decisions"])
    assert any("another cow in the way" in d for d in j["decisions"])


def test_a_recognised_cow_gets_a_walking_check_on_her_side_on_frames_at_most_every_ten_minutes(client, device, admin, mixed_clip, monkeypatch):
    from gomitra.services import analysis, gait
    client.post("/api/demo/seed", headers=admin)
    monkeypatch.setattr(analysis, "analyze", lambda *a, **k: {"results": [{"cow": {"id": "rani", "name": "Rani"}, "finding": None, "alert": False}]})
    calls = []
    monkeypatch.setattr(gait, "analyze", lambda jpegs: calls.append(len(jpegs)) or
                        {"gait": {"score": 2, "summary": "stub"}, "posture": {"label": "lying"}, "overlay": None, "pose_used": True})
    one = client.post("/api/ingest", json={"file": mixed_clip}, headers=device).json()
    assert "pose model" in one["steps"] and one["posture"] == "lying" and len(calls) == 1 and 1 <= calls[0] <= 5
    two = client.post("/api/ingest", json={"file": mixed_clip}, headers=device).json()
    assert "pose model" not in two["steps"] and len(calls) == 1                  # rate-limited per cow
    assert client.get("/api/cows/rani/trends").json()["rest"]["samples"] == 1    # the sighting was kept for the habit trends


def test_the_devices_log_shows_what_was_routed_where(client, device):
    for name in ("walk_tharparkar.jpg", "sound_calm.wav"):
        client.post("/api/ingest", json={"file": sample_b64(name), "camera": "Cam"}, headers=device)
    rec = client.get("/api/ingest/recent").json()
    assert len(rec) == 2 and rec[0]["ts"] >= rec[1]["ts"] and all("summary" in e and "steps" in e for e in rec)
