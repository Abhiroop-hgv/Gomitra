"""Demo data: 12 demo cows and a SIMULATED week of habit data so the trend alerts can be shown.

The rules that raise the alerts are real; the history is made up. Because the trend windows are the 24-hour blocks before "now",
the simulated week is rebuilt when the app opens and it is more than 90 minutes old (`ensure_history`).
"""
import random
import uuid

from gomitra import config
from gomitra.context import store
from gomitra.core.util import now
from gomitra.domain import trends
from gomitra.services import alerts, ingest
from gomitra.services.cows import all_cows

DEMO_COWS = [("gauri", "Gauri", "0417", "Holstein-Friesian", "5 years"), ("nandini", "Nandini", "0388", "Holstein-Friesian cross", "6 years"),
             ("rani", "Rani", "0451", "Holstein-Friesian cross", "4 years"), ("kamala", "Kamala", "0452", "Holstein-Friesian", "6 years"),
             ("lakshmi", "Lakshmi", "0412", "Holstein-Friesian", "4 years"), ("radha", "Radha", "0405", "Holstein-Friesian cross", "6 years"),
             ("ganga", "Ganga", "0431", "Holstein-Friesian cross", "3 years"), ("yamuna", "Yamuna", "0426", "Holstein-Friesian", "5 years"),
             ("tulasi", "Tulasi", "0439", "Holstein-Friesian cross", "4 years"), ("saraswati", "Saraswati", "0398", "Holstein-Friesian", "7 years"),
             ("kavya", "Kavya", "0444", "Holstein-Friesian cross", "2 years"), ("sita", "Sita", "0409", "Holstein-Friesian cross", "5 years")]
HISTORY_CAMERA = "North field camera"
# resting sightings out of 12 per day: (usual day, last 24 h). Tulasi rests far more than her usual; the others do not.
HISTORY_REST = {"tulasi": (5, 9), "kamala": (5, 5), "lakshmi": (5, 6), "nandini": (5, 5)}
HISTORY_GAIT = {"nandini": [1, 1, 1, 2, 2]}        # oldest first, one score per day over the last 5 days
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
    for col in ("observations", "alerts", "audio_events", "posture_log", "ingest_log", "meta"):
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
    for cid in HISTORY_REST:
        if store.get("cows", cid):
            tr = alerts.check_cow(cid)
            out["cows"][cid] = {k: tr[k] for k in ("today", "base", "flag")}
    out["eating"] = alerts.check_eating(HISTORY_CAMERA)
    store.put("meta", "demo_history", {"ts": now()})
    return out
