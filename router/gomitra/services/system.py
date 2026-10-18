"""Read-only views for the app (chewing and sounds, cow trends, vet report), service status, and the pose-service warm-up."""
import logging
import os

from gomitra import config
from gomitra.context import kb, store
from gomitra.core import tracing as trace
from gomitra.core.util import now
from gomitra.domain import suspects, trends
from gomitra.errors import BadRequest
from gomitra.infra import inference as inf
from gomitra.services import alerts, demo, gait, messages, report
from gomitra.services.cows import get_cow

_warm = {"at": 0.0}


def feeding(camera="Camera 1"):
    """Today's chewing activity for a camera group, from the eating-sound clips. Meals split at 5-minute gaps."""
    t = now()
    ev = [e for e in store.list_where("audio_events", "camera", camera) if e.get("chew") and t - 86400 <= e["ts"] < t]
    minutes, meals = trends.chew_minutes(ev, t - 86400, t)
    return {"camera": camera, "clips": len(ev), "meals": meals, "minutes": minutes}


def sounds(camera="North field camera"):
    """What the microphone group heard today: chewing time and meals, the latest distress call, and which cow to check first."""
    f = feeding(camera)
    ev = [e for e in store.list_where("audio_events", "camera", camera) if e.get("distress")]
    last = max((e["ts"] for e in ev), default=None)
    tr = alerts.check_eating(camera)
    open_ = [a for k in ("distress", "eating") for a in store.list_where("alerts", "kind", k)
             if a.get("camera") == camera and not a.get("resolved") and a.get("check_first") and now() - a["ts"] < 43200]
    latest = max(open_, key=lambda a: a["ts"], default=None)
    return dict(f, last_distress=last, distress_clips=len(ev), trend=tr,
                check_first=(latest or {}).get("check_first"), check_first_stands_out=(latest or {}).get("stands_out"))


def cow_trends(cid):
    get_cow(cid)
    entries = store.list_where("posture_log", "cow_id", cid)
    return {"rest": trends.rest_trend(entries, now()), "gait": trends.gait_trend(entries),
            "streak": suspects.lying_streak(entries, now())}


def vet_report(cid, lang="en"):
    """Handover note for the vet: facts from stored data, written up by Gemini (plain text if Gemini is down)."""
    if lang not in messages.LANGS:
        raise BadRequest("lang must be en, hi or te")
    trace.start()
    c = get_cow(cid)
    entries = store.list_where("posture_log", "cow_id", cid)
    facts = report.build_facts(c, store.list_where("observations", "cow_id", cid), trends.rest_trend(entries, now()),
                               trends.gait_trend(entries), alerts.check_eating(c.get("camera") or "Camera 1"), now())
    note, source = report.compose(facts, lang)
    return {"cow": c["name"], "lang": lang, "note": note, "source": source, "facts": facts, "time": now(), "trace": trace.get()}


def status():
    return {"infer_backend": inf.BACKEND, "project": inf.PROJECT, "region": inf.REGION,
            "endpoint_id": inf.ENDPOINT_ID or None, "gemini_model": messages.GEMINI_MODEL,
            "cows": len(store.list("cows")), "kb_sources": kb.sources(), "time": now()}


def warmup():
    """The app calls this when it opens, so the pose service (which sleeps when idle) is already awake by the time someone runs
    a walking check, and the simulated demo week is fresh. Runs one small check and waits for it, so the request keeps this
    service's CPU on. Skips the pose step if a warm-up ran in the last 4 minutes."""
    refreshed = False
    try:
        refreshed = demo.ensure_history()
    except Exception:
        logging.getLogger("gomitra").exception("demo history refresh failed")
    extra = {"demo_refreshed": True} if refreshed else {}
    if not gait.POSE_URL or now() - _warm["at"] < 240:
        return {"started": False, **extra}
    _warm["at"] = now()
    try:
        with open(os.path.join(config.STATIC_DIR, "samples", "walk_lame.jpg"), "rb") as f:
            gait.call_pose([f.read()])
        return {"started": True, "ok": True, **extra}
    except Exception as e:
        _warm["at"] = 0.0
        return {"started": True, "ok": False, "error": type(e).__name__, **extra}
