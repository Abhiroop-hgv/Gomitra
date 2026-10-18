"""Walking and resting check for one cow from 1 to 5 pictures: pose model -> standing/sitting/lying, Gemini -> gait score."""
import uuid

from gomitra.context import store
from gomitra.core import tracing as trace
from gomitra.core.util import now, read_image
from gomitra.domain import trends
from gomitra.errors import BadRequest
from gomitra.infra import inference as inf
from gomitra.services import gait, messages
from gomitra.services import notify
from gomitra.services.alerts import check_cow, raise_alert
from gomitra.services.cows import get_cow, public

LABELS = ("standing", "sitting", "lying")


def check_posture(images, cow_id=None, camera="Camera 1"):
    """Gait 3 or more raises a limp alert. For a known cow the standing/lying label and the gait score are saved as a sighting,
    which feeds the habit trends (resting more than usual, lying for hours, walking getting worse)."""
    if not images:
        raise BadRequest("images missing")
    trace.start()
    jpegs = [inf.shrink_jpeg(read_image(i), 960) for i in images[:5]]
    res = gait.analyze(jpegs)
    score = (res.get("gait") or {}).get("score")
    res["alert"], res["message"], res["cow"] = False, None, None
    if cow_id:
        _save_for_cow(cow_id, camera, jpegs, res, score)
    elif score is not None and score >= 3:
        res["message"] = messages.template("limp", "this cow")
    res["trace"] = trace.get()
    return res


def _save_for_cow(cow_id, camera, jpegs, res, score):
    c = get_cow(cow_id)
    sig = dict(c.get("signals") or {})
    if score is not None:
        sig["walking"] = "check" if score >= 3 else "watch" if score == 2 else "ok"
    if res.get("posture") and res["posture"].get("label") not in (None, "unknown"):
        sig["resting"] = res["posture"]["label"]
    store.update("cows", cow_id, {"signals": sig, "last_seen": now(), "gait_score": score})
    if score is not None and score >= 3:
        finding = {"kind": "limp", "p": round(score / 5, 2), "severity": "high" if score >= 4 else "medium"}
        upd = raise_alert(dict(c, signals=sig), finding, jpegs[0], None, camera)
        if res.get("overlay"):
            upd["scene"] = res["overlay"]
        store.update("cows", cow_id, upd)
        res["alert"], res["message"] = True, upd.get("msg") or c.get("msg")
        notify.send("limp", c["name"], finding["severity"], res["message"])
    label = (res.get("posture") or {}).get("label")
    if label in LABELS or score is not None:                      # keep a sighting for the habit trends
        store.put("posture_log", uuid.uuid4().hex, {"cow_id": cow_id, "ts": now(), "label": label if label in LABELS else None,
                                                    "gait": score})
        res["trend"] = {"rest": check_cow(cow_id), "gait": trends.gait_trend(store.list_where("posture_log", "cow_id", cow_id))}
    res["cow"] = public(get_cow(cow_id))
