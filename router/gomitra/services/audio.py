"""Sound clips: call-type (possible distress) and eating-sound models, stored as events; distress alerts."""
import uuid

from gomitra.context import infer, store
from gomitra.core import tracing as trace
from gomitra.core.util import now, read_image
from gomitra.domain import rules
from gomitra.errors import UpstreamError
from gomitra.services import messages
from gomitra.services.alerts import attach_suspects


def process_audio(audio, camera="Camera 1", immediate=False):
    """One clip. A distress alert needs two matching clips in 30 minutes, unless `immediate` (demo clips alert at once).
    The alert also says which cow to check first, from what the cameras saw of the cows in this group."""
    trace.start()
    res = infer.audio(read_image(audio))
    if res.get("error"):
        raise UpstreamError(res["error"])
    ts = now()
    finding = rules.distress_finding(res)
    prior = sorted([e for e in store.list_where("audio_events", "camera", camera) if ts - e["ts"] < 1800],
                   key=lambda e: e["ts"])[-2:]
    store.put("audio_events", uuid.uuid4().hex, {
        "camera": camera, "ts": ts, "usable": res.get("usable"), "distress": bool(finding),
        "p_hfc": (res.get("distress") or {}).get("p_hfc"), "chew": (res.get("bite_chew") or {}).get("label")})
    alert = None
    if finding and (immediate or sum(1 for e in prior if e.get("distress")) >= 1):
        msg, source = messages.compose("distress", camera, [], "medium", finding["p"])
        alert = {"kind": "distress", "camera": camera, "ts": ts, "severity": "medium", "msg": msg, "source": source,
                 "short": messages.SHORT["distress"], "resolved": False}
        store.put("alerts", uuid.uuid4().hex, attach_suspects(alert, camera))
    return {"audio": res, "finding": finding, "alert": alert, "trace": trace.get(),
            "note": "One clip is not enough: distress alerts need two matching clips in 30 minutes."
            if finding and not alert else None}
