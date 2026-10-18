"""domain/rules.py: when does a model result become a finding worth alerting on?"""
import pytest

from gomitra.domain import rules


@pytest.mark.parametrize("probs,expected", [
    ({"normal": 0.99, "lumpy": 0.005, "fmd": 0.005}, None),                       # healthy
    ({"normal": 0.30, "lumpy": 0.68, "fmd": 0.02}, ("lumpy", "medium")),          # above 0.60
    ({"normal": 0.02, "lumpy": 0.98, "fmd": 0.0}, ("lumpy", "high")),             # 0.85 or more is high
    ({"normal": 0.0, "fmd": 0.62, "lumpy": 0.0}, ("fmd", "high")),                # foot-and-mouth is always high
    ({"normal": 0.45, "lumpy": 0.55, "fmd": 0.0}, None),                          # below the 0.60 threshold
    ({"normal": 0.70, "lumpy": 0.65, "fmd": 0.0}, None),                          # normal is still larger
    (None, None),
    ({}, None),
])
def test_skin_finding(probs, expected):
    got = rules.skin_finding(probs)
    assert (got and (got["kind"], got["severity"])) == (expected or None)


def test_skin_finding_reports_the_probability():
    assert rules.skin_finding({"normal": 0.1, "lumpy": 0.9, "fmd": 0.0})["p"] == 0.9


def test_photos_alert_at_once_but_camera_frames_need_agreement():
    assert rules.confirmed([], "lumpy", cctv=False)
    assert not rules.confirmed([], "lumpy", cctv=True)                     # one sighting is not enough on camera
    assert rules.confirmed(["ok", "lumpy"], "lumpy", cctv=True)           # 2 of the last 5 agree
    assert not rules.confirmed(["lumpy", "ok", "ok", "ok", "ok"], "lumpy", cctv=True)     # the old one fell out of the window


def test_distress_needs_a_usable_clip_and_a_very_high_score():
    audio = {"usable": True, "distress": {"distress": True, "p_hfc": 0.99}}
    assert rules.distress_finding(audio) == {"kind": "distress", "p": 0.99, "severity": "medium"}
    assert rules.distress_finding({"usable": False, "distress": {"distress": True, "p_hfc": 1.0}}) is None
    assert rules.distress_finding({"usable": True, "distress": {"distress": True, "p_hfc": 0.8}}) is None
    assert rules.distress_finding({"usable": True, "distress": {"distress": False, "p_hfc": 0.95}}) is None
    assert rules.distress_finding(None) is None


def test_best_face_is_the_sharpest_usable_one():
    ident = {"faces": [{"usable": True, "conf": 0.6, "id": "a"}, {"usable": True, "conf": 0.9, "id": "b"},
                       {"usable": False, "conf": 0.99, "id": "c"}]}
    assert rules.best_face(ident)["id"] == "b"
    assert rules.best_face({"faces": []}) is None
    assert rules.best_face(None) is None
