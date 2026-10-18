"""Walking and resting check: frames -> pose service (keypoints, standing/sitting/lying) -> Gemini gait score 1-5.

Adapted from the team's gait_detection.py (Sprecher locomotion scale, trust gate, Indian-breed note).
If the pose service is not available the same Gemini question is asked from the pictures alone, and the answer says so.
"""
import base64
import json
import os
import time

from gomitra.core import tracing as trace
from gomitra.services import messages
POSE_URL = os.getenv("POSE_URL", "").rstrip("/")
SCALE = """Gait / locomotion score (Sprecher 1997):
1 = normal: level back, smooth even stride.
2 = mildly lame: back arches when walking, gait slightly abnormal.
3 = moderately lame: back always arched, short strides with one or more legs.
4 = lame: obvious limp, favours one or more limbs, back always arched.
5 = severely lame: cannot or will barely bear weight on a limb, strong reluctance to move."""
SCHEMA = {"type": "OBJECT", "properties": {"image_quality_ok": {"type": "BOOLEAN"}, "gait_score": {"type": "INTEGER"},
                                           "summary": {"type": "STRING"}},
          "required": ["image_quality_ok", "gait_score", "summary"]}
MIN_KP_CONF = 0.3


def call_pose(jpegs):
    """-> pose service JSON, or raises. Service-to-service call with a Google identity token."""
    import google.auth.transport.requests as gtr
    import google.oauth2.id_token as idt
    import requests
    token = idt.fetch_id_token(gtr.Request(), POSE_URL)
    with trace.step("Cloud Run (gomitra-pose)", "DeepLabCut SuperAnimal body points, asia-south1"):
        r = requests.post(f"{POSE_URL}/pose", json={"images": [base64.b64encode(j).decode() for j in jpegs]},
                          headers={"Authorization": f"Bearer {token}"}, timeout=290)
        r.raise_for_status()
    return r.json()


def intro(n, poses):
    kp = ""
    if poses:
        kp = ("\nEach frame comes with body-pose keypoints from a pose model: {name: [x, y, confidence]} in pixels "
              "(origin top-left, y grows downward). Low-confidence points are left out. Use them to check what you see "
              "(for example how far the mid-back sits above the line from neck to tail).")
    return f"""You are assisting a dairy-farm gait check on an Indian cattle breed. The goal is to notice EARLY gait change
before it becomes obvious lameness, so look closely for subtle signs and do not under-score a slightly abnormal gait.
Do not diagnose a cause.

Breed note: Indian cattle vary a lot in build. Many have a natural hump over the shoulders, a sloping rump, loose skin or
a lean frame. These traits are normal anatomy, not signs of lameness. Judge each animal against her own build: look for a
back that hunches upward behind the shoulders or loin, uneven or shortened steps, a head that nods, or a leg held or
placed oddly. Build alone must not raise the score.

{SCALE}

Below {'is 1 picture' if n == 1 else f'are {n} frames'} of the same cow{' walking, in time order' if n > 1 else ''}.{kp}
{'With a single picture you can only judge the standing posture (back line, head carriage, leg placement); say so in the summary.' if n == 1 else 'The frames are sparse, so you cannot see a full stride.'}
If the image is blurred, the cow is cut off or hidden, or not side-on, set image_quality_ok to false.
Answer with JSON only: image_quality_ok, gait_score (1-5), summary (ONE short line explaining the score)."""


def keypoints(pose):
    return {k: [round(v[0], 1), round(v[1], 1), round(v[2], 2)] for k, v in pose.items() if v[2] >= MIN_KP_CONF}


def ask_gemini(jpegs, poses):
    from google import genai
    from google.genai import types
    client = genai.Client(vertexai=True, project=messages.PROJECT, location=messages.GEMINI_LOCATION,
                          http_options=types.HttpOptions(timeout=60000))
    parts = [intro(len(jpegs), poses)]
    for i, j in enumerate(jpegs):
        if poses:
            parts.append(f"Frame {i + 1} keypoints: {json.dumps(keypoints(poses[i]))}")
        parts.append(types.Part.from_bytes(data=j, mime_type="image/jpeg"))
    last = None
    for delay in (0, 4, 10):
        time.sleep(delay)
        try:
            with trace.step("Gemini on Vertex AI", f"{messages.GEMINI_MODEL}, walking score (Sprecher scale)"):
                r = client.models.generate_content(model=messages.GEMINI_MODEL, contents=parts,
                                                   config=types.GenerateContentConfig(response_mime_type="application/json",
                                                                                      response_schema=SCHEMA, temperature=0.0))
            return r.text
        except Exception as e:                      # retry only overload / rate limit
            last = e
            if not any(m in f"{e}" for m in ("429", "503", "RESOURCE_EXHAUSTED", "UNAVAILABLE")):
                raise
    raise last


def trust_gate(text):
    """(score or None, summary). A score is kept only if the picture was good enough and the score is an integer 1-5."""
    try:
        d = json.loads(text)
    except (TypeError, ValueError):
        return None, "The answer could not be read."
    summary = str(d.get("summary", "")).strip()
    if d.get("image_quality_ok") is not True:
        return None, summary or "The picture is not clear enough."
    s = d.get("gait_score")
    if isinstance(s, bool) or not isinstance(s, int) or not 1 <= s <= 5:
        return None, "No valid score."
    return s, summary


def analyze(jpegs):
    """jpegs: 1-5 JPEG byte strings of one cow. -> result dict for the app."""
    t = time.time()
    out = {"frames": len(jpegs), "pose_used": False, "overlay": None, "posture": None, "keypoints_found": 0, "pose_error": None}
    poses = None
    if POSE_URL:
        try:
            p = call_pose(jpegs)
            poses = [{k: tuple(v) for k, v in fp.items()} for fp in p["poses"]]
            best = p["posture"][p["best"]]
            out.update(pose_used=True, overlay="data:image/jpeg;base64," + p["overlay_b64"], posture=best,
                       keypoints_found=len(keypoints(poses[p["best"]])), pose_seconds=p["seconds"])
        except Exception as e:
            out["pose_error"] = f"{type(e).__name__}"
            poses = None
    try:
        score, summary = trust_gate(ask_gemini(jpegs, poses))
    except Exception as e:
        score, summary = None, f"Gait scoring is unavailable ({type(e).__name__})."
    out["gait"] = {"score": score, "summary": summary}
    out["seconds"] = round(time.time() - t, 1)
    return out
