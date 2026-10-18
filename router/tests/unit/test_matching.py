"""domain/matching.py: which registered cow is this?"""
import numpy as np

from gomitra.domain import matching


def unit(*v):
    a = np.array(v, np.float32)
    return (a / np.linalg.norm(a)).tolist()


COWS = [{"id": "gauri", "name": "Gauri", "tag": "0417", "embeddings": [{"v": unit(1, 0, 0)}, {"v": unit(0.9, 0.1, 0)}]},
        {"id": "rani", "name": "Rani", "tag": "0451", "embeddings": [{"v": unit(0, 1, 0)}]},
        {"id": "new", "name": "New", "tag": "0999", "embeddings": []}]


def ident(vec, conf=0.9):
    return {"faces": [{"usable": True, "conf": conf, "embedding": vec, "box": [0, 0, 10, 10]}]}


def test_the_closest_cow_above_the_threshold_is_matched():
    cow, score = matching.match_face(ident(unit(1, 0.05, 0)), COWS)
    assert cow["id"] == "gauri" and score > 0.99


def test_below_the_threshold_nobody_is_matched_but_the_best_score_is_returned():
    cow, score = matching.match_face(ident(unit(0.5, 0.5, 0.7)), COWS)
    assert cow is None and 0 < score < matching.config.FACE_MATCH


def test_no_usable_face_or_no_registered_faces():
    assert matching.match_face({"faces": []}, COWS) == (None, 0.0)
    assert matching.match_face(ident(unit(1, 0, 0)), [COWS[2]]) == (None, 0.0)


def test_a_custom_threshold_can_be_given():
    assert matching.match_face(ident(unit(0.7, 0.7, 0)), COWS, threshold=0.5)[0] is not None


def test_ear_tag_matches_ignoring_leading_zeros():
    ocr = {"faces": [{"tags": [{"read": {"number": "417"}}]}]}
    assert matching.match_tag(ocr, COWS)["id"] == "gauri"
    assert matching.match_tag({"faces": [{"tags": [{"read": {"number": "123"}}]}]}, COWS) is None
    assert matching.match_tag({"faces": [{"tags": [{"read": None}]}]}, COWS) is None
    assert matching.match_tag(None, COWS) is None


def test_face_in_box_picks_the_face_whose_centre_is_inside():
    ident_ = {"faces": [{"usable": True, "box": [10, 10, 30, 30], "conf": 0.9}, {"usable": True, "box": [200, 10, 220, 30], "conf": 0.9},
                        {"usable": False, "box": [50, 50, 60, 60], "conf": 0.9}]}
    assert matching.face_in_box(ident_, [0, 0, 100, 100])["faces"][0]["box"] == [10, 10, 30, 30]
    assert matching.face_in_box(ident_, [150, 0, 300, 100])["faces"][0]["box"] == [200, 10, 220, 30]
    assert matching.face_in_box(ident_, [300, 300, 400, 400]) is None
    assert matching.face_in_box({"faces": [{"usable": False, "box": [50, 50, 60, 60]}]}, [0, 0, 100, 100]) is None
