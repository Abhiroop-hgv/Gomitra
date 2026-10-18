"""Alert use-cases: turning findings and habit trends into alerts on cows or on a camera group.

Each alert carries a message in English, Hindi and Telugu written by Gemini from vet-document passages (fixed templates if
Gemini is unavailable). Habit alerts: resting more than usual (`rest`), lying for hours (`down`), group chewing low (`eating`).
Sound alerts also say which cow to check first (see domain/suspects.py).
"""
import logging
import uuid

from gomitra.context import kb, store
from gomitra.core.util import data_url, now
from gomitra.domain import suspects, trends
from gomitra.services import messages, notify
from gomitra.services.cows import all_cows, get_cow

TREND_QUERY = {"rest": "cow lying down more than usual and not eating what to do",
               "down": "cow lying down for hours will not get up what to do",
               "eating": "cow eating less loss of appetite what to do"}
FINDING_QUERY = {"lumpy": "lumpy skin disease what to do", "fmd": "foot and mouth disease what to do",
                 "limp": "lameness limping what to do"}
_eat_cache = {}


def clear_cache():
    _eat_cache.clear()


def _passages(query):
    try:
        return kb.search(query)
    except Exception:
        return []


def trend_message(kind, name, severity="medium"):
    return messages.compose(kind, name, _passages(TREND_QUERY[kind]), severity, None)


def raise_alert(c, finding, scene_jpeg, box, camera):
    """The fields to store on a cow for a confirmed finding; the message is rewritten only when the finding changes."""
    kind = finding["kind"]
    upd = {"alert": True, "kind": kind, "severity": finding["severity"], "camera": camera, "box": box,
           "scene": data_url(scene_jpeg), "last_seen": now(), "short": messages.SHORT[kind],
           "signals": dict(c.get("signals") or {}, **{("walking" if kind == "limp" else "skin"): "check"})}
    if c.get("kind") != kind or not c.get("msg"):
        upd["msg"], upd["source"] = messages.compose(kind, c["name"], _passages(FINDING_QUERY[kind]),
                                                     finding["severity"], finding["p"])
    return upd


def check_rest(cid):
    """Compare her resting share in the last 24 h with her own previous week; alert on a clear rise. -> trend dict."""
    c = get_cow(cid)
    tr = trends.rest_trend(store.list_where("posture_log", "cow_id", cid), now())
    if tr["flag"] and not c.get("alert"):
        msg, source = trend_message("rest", c["name"])
        store.update("cows", cid, {"alert": True, "kind": "rest", "severity": "medium", "short": messages.SHORT["rest"],
                                   "msg": msg, "source": source, "last_seen": now(), "box": None})
        notify.send("rest", c["name"], "medium", msg)
    return tr


def check_down(cid):
    """Has she been lying at every recent sighting for hours, without standing? High-severity alert, worded for 'go and look now'.
    Replaces a milder 'rest' alert but never a disease alert. -> the lying-streak dict."""
    c = get_cow(cid)
    st = suspects.lying_streak(store.list_where("posture_log", "cow_id", cid), now())
    if suspects.down_flag(st) and (not c.get("alert") or c.get("kind") == "rest"):
        msg, source = trend_message("down", c["name"], "high")
        if check_eating(c.get("camera") or "Camera 1")["flag"]:                  # sound agrees: say so
            for lang in messages.LANGS:
                msg[lang]["text"] = (msg[lang]["text"] + " " + suspects.ALSO_CHEWING[lang]).strip()
        store.update("cows", cid, {"alert": True, "kind": "down", "severity": "high", "short": messages.SHORT["down"],
                                   "msg": msg, "source": source, "last_seen": now(), "box": None})
        notify.send("down", c["name"], "high", msg)
    return st


def check_cow(cid):
    """All habit checks for one cow after a new sighting. -> the resting trend dict."""
    check_down(cid)
    return check_rest(cid)


def check_eating(camera):
    """Group chewing in the last 24 h against the previous week. One open alert per camera group. Cached for a minute."""
    hit = _eat_cache.get(camera)
    if hit and now() - hit[0] < 60:
        return hit[1]
    tr = trends.eat_trend(store.list_where("audio_events", "camera", camera), now())
    if tr["flag"]:
        open_ = [a for a in store.list_where("alerts", "kind", "eating")
                 if a.get("camera") == camera and not a.get("resolved") and now() - a["ts"] < 43200]
        if not open_:
            msg, source = trend_message("eating", camera)
            alert = {"kind": "eating", "camera": camera, "ts": now(), "severity": "medium",
                     "msg": msg, "source": source, "short": messages.SHORT["eating"], "resolved": False}
            store.put("alerts", uuid.uuid4().hex, attach_suspects(alert, camera))
            notify.send("eating", camera, "medium", alert["msg"])
    _eat_cache[camera] = (now(), tr)
    return tr


def rank_suspects(camera):
    """Rank the cows of one camera group by how inactive or odd their recent sightings look. -> suspects.rank result."""
    t, scored = now(), []
    for c in all_cows():
        if (c.get("camera") or "Camera 1") != camera:
            continue
        entries = store.list_where("posture_log", "cow_id", c["id"])
        scored.append(suspects.score_cow(c, entries, trends.rest_trend(entries, t), trends.gait_trend(entries), t))
    return suspects.rank(scored)


def attach_suspects(alert, camera):
    """Add 'check this cow first' to a sound alert, in the three languages, and keep the ranking on the alert."""
    try:
        res = rank_suspects(camera)
    except Exception:
        logging.getLogger("gomitra").exception("suspect ranking failed")
        return alert
    line = suspects.lines(res)
    for lang in messages.LANGS:
        m = alert["msg"][lang]
        m["advice"] = (m.get("advice", "") + " " + line[lang]).strip()
    alert["check_first"] = line
    alert["suspects"] = [{"id": c["id"], "name": c["name"], "score": c["score"]} for c in res["ranked"][:3]]
    alert["stands_out"] = res["stands_out"]
    return alert


def list_open():
    out = [a for a in store.list("alerts") if not a.get("resolved")]
    return sorted(out, key=lambda a: -a["ts"])[:20]


def resolve(aid):
    store.update("alerts", aid, {"resolved": True})
