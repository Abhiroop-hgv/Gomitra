"""Demo data: 12 demo cows and a SIMULATED week of habit data so the trend alerts can be shown.

The rules that raise the alerts are real; the history is made up. Because the trend windows are the 24-hour blocks before "now",
the simulated week is rebuilt when the app opens and it is more than 90 minutes old (`ensure_history`).
"""
import os
import random
import uuid

from gomitra import config
from gomitra.context import store
from gomitra.core.util import data_url, now
from gomitra.domain import trends
from gomitra.services import alerts, ingest, messages, notify
from gomitra.services.cows import all_cows

DEMO_COWS = [("rani", "Rani", "0451", "Gir cross", "4 years"), ("tulasi", "Tulasi", "0439", "Holstein-Friesian", "5 years"),
             ("kamala", "Kamala", "0452", "Gir cross", "6 years"), ("ganga", "Ganga", "0431", "Nandi cross", "7 years"),
             ("gauri", "Gauri", "0417", "Sahiwal cross", "1 year"), ("lakshmi", "Lakshmi", "0412", "Gir cross", "1 year")]
HISTORY_CAMERA = "North field camera"
BARN_CAMERA = "Barn camera"                       # Rani is on her own camera, so a sound alert there can name her
LUMPY_BOX = [0.02, 0.02, 0.99, 0.98]              # the box the skin model draws on the demo photo (samples/lumpy_demo.jpg)
# resting sightings out of 12 per day: (usual day, last 24 h). Tulasi rests far more than her usual; the others do not.
HISTORY_REST = {"tulasi": (5, 9), "kamala": (5, 5), "lakshmi": (5, 6), "ganga": (5, 5)}
HISTORY_GAIT = {"ganga": [1, 1, 1, 2, 2]}          # oldest first, one score per day over the last 5 days
HISTORY_REFRESH = 90 * 60                          # rebuild when older than this ("down for hours" needs a sighting from the last 3 hours)
_hist_check = {"at": 0.0}


def seed():
    """Add the demo cows that are missing. -> number added."""
    n = 0
    for cid, name, tag, breed, age in DEMO_COWS:
        if not store.get("cows", cid):
            store.put("cows", cid, {"name": name, "tag": tag, "breed": breed, "age": age, "camera": HISTORY_CAMERA,
                                    "alert": False, "history": [], "last_seen": now(), "embeddings": [], "demo": True,
                                    "created": now()})
            n += 1
    return n


def ensure_history():
    """Called when the app opens: rebuild the simulated week if it is missing or old, so the demo cows always match the
    test guide, whenever the jury looks. Turn off with AUTO_DEMO=0. -> True if it rebuilt."""
    if not config.AUTO_DEMO or now() - _hist_check["at"] < 120:
        return False
    _hist_check["at"] = now()
    m = store.get("meta", "demo_history")
    if (m and now() - m["ts"] < HISTORY_REFRESH) or not store.get("cows", "tulasi"):
        return False
    store.put("meta", "demo_history", {"ts": now()})          # claim it first, so two visitors do not both rebuild
    build_history()
    return True


def reset(keep_cows=False):
    """Back to a clean demo: removes all alerts, observations, sound events, sightings and device logs, clears every cow's
    alert and history, deletes cows that are not demo cows (unless keep_cows), then reloads the demo cows and the simulated
    week. The vet documents are not touched."""
    for col in ("observations", "alerts", "audio_events", "posture_log", "ingest_log", "notifications", "meta"):
        store.delete_many(col, [d["id"] for d in store.list(col)])
    removed = 0
    for c in all_cows():
        if c.get("demo"):
            store.update("cows", c["id"], {"alert": False, "kind": None, "severity": None, "short": None, "msg": None,
                                           "source": None, "box": None, "signals": {}, "history": [], "scene": None,
                                           "gait_score": None, "camera": HISTORY_CAMERA, "last_seen": now()})
        elif not keep_cows:
            store.delete("cows", c["id"])
            removed += 1
    added = seed()
    alerts.clear_cache()
    ingest.clear_state()
    return {"cows_removed": removed, "demo_cows_added": added, "history": build_history()}


def _posture_history(t0, rng):
    """12 sightings a day for 8 days per cow in HISTORY_REST. Newest first within a day; Tulasi has been down for hours."""
    posture = []
    for cid, (usual, today) in HISTORY_REST.items():
        c = store.get("cows", cid)
        if not c:
            continue
        if c.get("kind") in ("rest", "down"):
            store.update("cows", cid, {"alert": False, "kind": None, "short": None, "msg": None, "severity": None})
        for k in range(trends.WINDOWS):
            n_rest = today if k == 0 else usual + rng.choice((-1, 0, 0, 1))
            labels = [("sitting" if i % 4 == 3 else "lying") for i in range(n_rest)] + ["standing"] * (12 - n_rest)
            rng.shuffle(labels)
            if k == 0:
                if cid == "tulasi":
                    labels = ["lying"] * 4 + [l for l in labels if l == "standing"] + ["lying"] * (n_rest - 4)
                    rest = labels[4:]
                    rng.shuffle(rest)
                    labels = labels[:4] + rest
                elif "standing" in labels:      # everyone else was seen standing most recently
                    j = labels.index("standing")
                    labels[0], labels[j] = labels[j], labels[0]
            for i, lab in enumerate(labels):
                e = {"cow_id": cid, "ts": t0 - k * trends.DAY - (i + 0.5) * 7200, "label": lab, "gait": None, "demo": True}
                if i == 0 and cid in HISTORY_GAIT and k < len(HISTORY_GAIT[cid]):
                    e["gait"] = HISTORY_GAIT[cid][len(HISTORY_GAIT[cid]) - 1 - k]
                posture.append((uuid.uuid4().hex, e))
    return posture


def _chewing_history(t0, rng):
    """Group chewing clips: 4 meals a day for 7 days, but only 2 meals in the last 24 hours."""
    chew = []
    for k in range(trends.WINDOWS):
        starts = (6, 17) if k == 0 else (2, 8, 14, 20)           # hours into the day
        for h in starts:
            for j in range(rng.choice((11, 12, 13))):
                ts = t0 - (k + 1) * trends.DAY + h * 3600 + j * 120
                chew.append((uuid.uuid4().hex, {"camera": HISTORY_CAMERA, "ts": ts, "usable": True, "distress": False,
                                                "p_hfc": 0.0, "chew": "chewing", "demo": True}))
    return chew


def build_history():
    """Replace the simulated week (safe to repeat) and run the habit checks on it, so the alerts appear."""
    t0, rng = now(), random.Random(7)
    for col in ("posture_log", "audio_events"):
        store.delete_many(col, [d["id"] for d in store.list_where(col, "demo", True)])
    for a in store.list_where("alerts", "kind", "eating"):
        if a.get("camera") == HISTORY_CAMERA:
            store.update("alerts", a["id"], {"resolved": True})
    posture = _posture_history(t0, rng)
    store.put_many("posture_log", posture)
    chew = _chewing_history(t0, rng)
    store.put_many("audio_events", chew)
    alerts.clear_cache()
    out = {"posture_sightings": len(posture), "chew_clips": len(chew), "cows": {}}
    with notify.muted():
        for cid in HISTORY_REST:
            if store.get("cows", cid):
                tr = alerts.check_cow(cid)
                out["cows"][cid] = {k: tr[k] for k in ("today", "base", "flag")}
        out["eating"] = alerts.check_eating(HISTORY_CAMERA)
    with notify.muted():
        out["scenarios"] = _scenarios(t0)
    store.put("meta", "demo_history", {"ts": now()})
    return out


def _scenarios(t0):
    """The two stories the demo tells besides Tulasi: Rani's group hears a loud distress call, and Kamala has lumpy skin.
    The alert rules and messages are the real ones; the sound clips and Kamala's photo are the demo inputs."""
    done = []
    if store.get("cows", "rani"):
        for a in store.list_where("alerts", "kind", "distress"):
            if a.get("demo"):
                store.delete("alerts", a["id"])
        store.update("cows", "rani", {"camera": BARN_CAMERA})
        store.put_many("posture_log", [(uuid.uuid4().hex, {"cow_id": "rani", "ts": t0 - 60 - i * 3600, "label": "lying", "gait": None,
                                                          "demo": True}) for i in range(6)])
        store.put_many("audio_events", [(uuid.uuid4().hex, {"camera": BARN_CAMERA, "ts": t0 - k * 40, "usable": True, "distress": True,
                                                            "p_hfc": 0.97, "chew": None, "demo": True}) for k in (1, 0)])
        msg, source = messages.compose("distress", BARN_CAMERA, [], "medium", 0.97)
        alert = {"kind": "distress", "camera": BARN_CAMERA, "ts": t0, "severity": "medium", "msg": msg, "source": source,
                 "short": messages.SHORT["distress"], "resolved": False, "demo": True}
        alerts.attach_suspects(alert, BARN_CAMERA)
        store.put("alerts", uuid.uuid4().hex, alert)
        store.update("cows", "rani", {"alert": True, "kind": "distress", "severity": "medium", "short": messages.SHORT["distress"],
                                      "msg": alert["msg"], "source": source, "last_seen": now(), "box": None})
        done.append("rani")
    if store.get("cows", "kamala"):
        with open(os.path.join(config.STATIC_DIR, "samples", "lumpy_demo.jpg"), "rb") as f:
            jpeg = f.read()
        finding = {"kind": "lumpy", "p": 0.988, "severity": "high"}
        try:
            upd = alerts.raise_alert(store.get("cows", "kamala") | {"id": "kamala"}, finding, jpeg, LUMPY_BOX, HISTORY_CAMERA)
        except Exception:                                    # no vet-document search available: use the template wording
            upd = {"alert": True, "kind": "lumpy", "severity": "high", "camera": HISTORY_CAMERA, "box": LUMPY_BOX, "scene": data_url(jpeg),
                   "last_seen": now(), "short": messages.SHORT["lumpy"], "signals": {"skin": "check"}}
            upd["msg"], upd["source"] = messages.compose("lumpy", "Kamala", [], "high", 0.988, use_gemini=False)
        store.update("cows", "kamala", upd)
        done.append("kamala")
    return done
