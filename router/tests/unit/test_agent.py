"""domain/agent.py: the frame agent keeps the good frames and decides which model each goes to. No models needed here."""
import cv2
import numpy as np

from gomitra.domain import agent


def jpeg(img):
    return cv2.imencode(".jpg", img)[1].tobytes()


def textured(seed=0, size=(480, 640)):
    """A sharp frame (noise has a high Laplacian variance). Each seed has a different overall brightness, so frames with
    different seeds are not near-duplicates of each other once shrunk."""
    rng = np.random.default_rng(seed)
    noise = rng.integers(-40, 41, (size[0], size[1], 3))
    return np.clip(70 + 10 * seed + noise, 0, 255).astype(np.uint8)


# ---- stage 1: cheap checks on the router
def test_screen_keeps_a_sharp_frame():
    kept, dropped = agent.screen([(0.0, jpeg(textured()))])
    assert len(kept) == 1 and not dropped and kept[0]["t"] == 0.0


def test_screen_drops_dark_blurred_duplicate_and_unreadable_frames():
    good = textured(1)
    frames = [(0.0, jpeg(good)),
              (0.3, jpeg((good * 0.05).astype(np.uint8))),              # dark
              (0.7, jpeg(cv2.GaussianBlur(good, (0, 0), 25))),          # blurred
              (1.0, jpeg(good)),                                        # the same as the first
              (1.3, b"not an image"),
              (1.7, jpeg(textured(2)))]                                 # different and sharp
    kept, dropped = agent.screen(frames)
    assert [k["t"] for k in kept] == [0.0, 1.7]
    assert dropped == {"unreadable": 1, "too dark/bright": 1, "blurred": 1, "near-duplicate": 1}


def test_screen_keeps_only_the_sharpest_few_in_time_order():
    frames = [(float(i), jpeg(textured(i))) for i in range(12)]
    kept, dropped = agent.screen(frames, max_candidates=5)
    assert len(kept) == 5 and dropped["not among the sharpest"] == 7
    assert [k["t"] for k in kept] == sorted(k["t"] for k in kept)


# ---- stage 2: what the detector found in one frame
def info(w=640, h=480):
    return {"idx": 0, "t": 0.0, "w": w, "h": h, "img": np.full((h, w, 3), 120, np.uint8), "jpeg": b"x"}


def cow(box, conf=0.9, usable=True, reason=""):
    return {"box": box, "cow_conf": conf, "usable": usable, "reason": reason}


def test_a_fully_visible_side_on_cow_is_good_for_skin_and_gait():
    a = agent.assess(info(), [cow([100, 120, 540, 400])], [])
    assert a["skin_ok"] and a["gait_ok"] and a["view"] == "side-on" and a["why"] == ""


def test_a_cow_cut_off_by_the_edge_is_not_a_gait_frame():
    a = agent.assess(info(), [cow([0, 120, 440, 400])], [])
    assert a["skin_ok"] and not a["gait_ok"] and "cut off" in a["why"]


def test_another_cow_in_the_way_blocks_the_gait_frame():
    a = agent.assess(info(), [cow([100, 120, 540, 400]), cow([120, 140, 500, 390])], [])
    assert not a["gait_ok"] and "in the way" in a["why"]


def test_a_cow_facing_the_camera_is_not_side_on():
    a = agent.assess(info(), [cow([250, 100, 390, 420])], [])
    assert not a["gait_ok"] and a["view"] != "side-on" and "not side-on" in a["why"]


def test_a_tiny_cow_is_good_for_nothing():
    a = agent.assess(info(), [cow([300, 200, 340, 230])], [])
    assert not a["gait_ok"] and not a["skin_ok"]


def test_a_low_confidence_detection_is_ignored():
    assert agent.assess(info(), [cow([100, 120, 540, 400], conf=0.3)], [])["why"] == "no cow found"


def test_a_clear_face_makes_a_face_frame_even_without_a_body():
    a = agent.assess(info(), [], [{"usable": True, "conf": 0.8, "box": [1, 1, 2, 2]}, {"usable": False, "conf": 0.99, "box": [1, 1, 2, 2]}])
    assert a["face"]["conf"] == 0.8 and a["view"] == "face"


# ---- stage 3: routing
def frame(t, box, faces=()):
    f = info()
    f["t"], f["jpeg"] = t, f"frame{t}".encode()
    return agent.assess(f, [cow(box)], list(faces))


def test_choose_routes_by_what_each_frame_shows():
    good = [frame(0.0, [100, 120, 540, 400]), frame(1.0, [110, 125, 545, 405]), frame(1.2, [105, 120, 540, 400])]
    cut = frame(2.0, [0, 120, 440, 400])
    face = frame(3.0, [250, 100, 390, 420], faces=[{"usable": True, "conf": 0.9, "box": [1, 1, 2, 2]}])
    plan = agent.choose(good + [cut, face])
    assert plan["face"] is face and plan["skin"] is not None
    assert [g["t"] for g in plan["gait"]] == [0.0, 1.0]            # 1.2 s is too close to 1.0 s; the cut-off frame is not used
    assert any("cow-face model" in d for d in plan["decisions"]) and any("pose model" in d for d in plan["decisions"])
    assert any("cut off" in d for d in plan["drops"])


def test_choose_with_nothing_usable_returns_an_empty_plan():
    plan = agent.choose([agent.assess(info(), [], [])])
    assert plan["skin"] is None and plan["face"] is None and plan["gait"] == []
    assert plan["drops"] and "no cow" in plan["drops"][0]


def test_at_most_five_gait_frames():
    plan = agent.choose([frame(float(i), [100, 120, 540, 400]) for i in range(9)])
    assert len(plan["gait"]) == agent.GAIT_FRAMES
