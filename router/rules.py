"""Alert rules: model output -> a finding the farmer should hear about, or nothing.

These are screening rules, not diagnoses. Thresholds are starting points and need tuning on real farm data.
"""
LUMPY_P = 0.60        # P(lumpy) at or above this counts as a skin finding
FMD_P = 0.60          # P(foot-and-mouth) at or above this
HIGH_P = 0.85         # at or above this the severity is "high"
DISTRESS_P = 0.90     # the distress model is overconfident, so only very high scores count
CCTV_NEED, CCTV_WINDOW = 2, 5     # CCTV frames: flag only if 2 of the last 5 sightings agree


def skin_finding(probs):
    """{"normal","lumpy","fmd"} probabilities -> {"kind","p","severity"} or None."""
    if not probs:
        return None
    kind = max(("lumpy", "fmd"), key=lambda k: probs.get(k, 0))
    p = probs.get(kind, 0)
    if p < (LUMPY_P if kind == "lumpy" else FMD_P) or p < probs.get("normal", 0):
        return None
    return {"kind": kind, "p": round(p, 3), "severity": "high" if (p >= HIGH_P or kind == "fmd") else "medium"}


def confirmed(history, kind, cctv):
    """history: this cow's earlier skin findings, newest last. Photos count at once; CCTV needs agreement."""
    if not cctv:
        return True
    recent = history[-(CCTV_WINDOW - 1):]
    return sum(1 for h in recent if h == kind) + 1 >= CCTV_NEED


def distress_finding(audio):
    d = (audio or {}).get("distress") or {}
    if not (audio or {}).get("usable") or not d.get("distress") or d.get("p_hfc", 0) < DISTRESS_P:
        return None
    return {"kind": "distress", "p": d["p_hfc"], "severity": "medium"}


def best_face(ident):
    """The sharpest usable face from an identify result, or None."""
    faces = [f for f in (ident or {}).get("faces", []) if f.get("usable")]
    return max(faces, key=lambda f: f["conf"]) if faces else None
