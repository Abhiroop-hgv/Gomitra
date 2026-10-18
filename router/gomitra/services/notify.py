"""Tell the farmer by SMS when a new alert is raised.

Google Cloud has no general SMS-sending service, so the text message goes through an SMS provider (Twilio here); the provider's
keys are plain environment settings (store them in Secret Manager in production). With no provider configured the message is only
logged ("logged, not sent") so the flow can be shown without sending anything. Every attempt is saved in `notifications` and
shown on the app's system screen / `GET /api/notifications`.

Safety: never raises (a failed SMS must not break an alert), skips repeats of the same alert for 6 hours, and stops at a daily cap.
"""
import base64
import json
import logging
import os
import urllib.parse
import urllib.request
import uuid
from contextlib import contextmanager

from gomitra.context import store
from gomitra.core.util import now
from gomitra.services import messages

PROVIDER = os.getenv("SMS_PROVIDER", "log")             # "fast2sms", "twilio" or "log"
TWILIO_SID = os.getenv("TWILIO_SID", "")
TWILIO_TOKEN = os.getenv("TWILIO_TOKEN", "")
TWILIO_FROM = os.getenv("TWILIO_FROM", "")
FAST2SMS_KEY = os.getenv("FAST2SMS_KEY", "")
FAST2SMS_ROUTE = os.getenv("FAST2SMS_ROUTE", "q")       # "q" = quick route (no DLT template, dearer); "dlt" needs FAST2SMS_SENDER and FAST2SMS_TEMPLATE
FAST2SMS_SENDER = os.getenv("FAST2SMS_SENDER", "")
FAST2SMS_TEMPLATE = os.getenv("FAST2SMS_TEMPLATE", "")
REPEAT_SECONDS = 6 * 3600       # the same alert on the same cow/camera is not sent again within this time
DAILY_CAP = 20                  # SMS per 24 h, so a bad day cannot run up a bill
MAX_CHARS = 300
SETTINGS = ("notify_settings", "main")
_muted = [0]


@contextmanager
def muted():
    """No SMS inside the block (rebuilding the simulated demo week must not text the farmer)."""
    _muted[0] += 1
    try:
        yield
    finally:
        _muted[0] -= 1


def get_settings():
    s = store.get(*SETTINGS) or {}
    return {"phone": s.get("phone", ""), "lang": s.get("lang", "en"), "enabled": bool(s.get("enabled", False)),
            "min_severity": s.get("min_severity", "medium")}


def set_settings(phone, lang="en", enabled=True, min_severity="medium"):
    phone = "".join(ch for ch in (phone or "") if ch.isdigit() or ch == "+")
    if enabled and not (phone.startswith("+") and 10 <= len(phone) <= 16):
        raise ValueError("phone must be in international form, for example +919876543210")
    if lang not in messages.LANGS:
        raise ValueError("lang must be one of en, hi, te")
    if min_severity not in ("medium", "high"):
        raise ValueError("min_severity must be medium or high")
    store.put(*SETTINGS, {"phone": phone, "lang": lang, "enabled": bool(enabled), "min_severity": min_severity})
    return public_settings()


def mask(phone):
    return phone[:3] + "*" * max(len(phone) - 6, 0) + phone[-3:] if len(phone) > 6 else phone


def public_settings():
    s = get_settings()
    return dict(s, phone=mask(s["phone"]), provider=PROVIDER, ready=PROVIDER == "log" or _configured())


def _configured():
    if PROVIDER == "twilio":
        return bool(TWILIO_SID and TWILIO_TOKEN and TWILIO_FROM)
    if PROVIDER == "fast2sms":
        return bool(FAST2SMS_KEY) and (FAST2SMS_ROUTE != "dlt" or bool(FAST2SMS_SENDER and FAST2SMS_TEMPLATE))
    return False


def build_text(kind, subject, msg, lang):
    m = (msg or {}).get(lang) or (msg or {}).get("en") or {}
    text = "GoMitra: %s - %s. %s" % (subject, m.get("title", kind), m.get("advice") or m.get("text", ""))
    return text[:MAX_CHARS]


def _send_twilio(to, text):
    url = "https://api.twilio.com/2010-04-01/Accounts/%s/Messages.json" % TWILIO_SID
    body = urllib.parse.urlencode({"To": to, "From": TWILIO_FROM, "Body": text}).encode()
    req = urllib.request.Request(url, data=body)
    req.add_header("Authorization", "Basic " + base64.b64encode(("%s:%s" % (TWILIO_SID, TWILIO_TOKEN)).encode()).decode())
    with urllib.request.urlopen(req, timeout=10) as r:
        return r.status in (200, 201)


def _send_fast2sms(to, text):
    """Fast2SMS bulkV2 (Indian numbers only). `to` is +91XXXXXXXXXX; the API wants the 10 digits."""
    digits = "".join(ch for ch in to if ch.isdigit())
    if not (digits.startswith("91") and len(digits) == 12):
        raise ValueError("Fast2SMS sends to Indian numbers (+91...)")
    fields = {"route": FAST2SMS_ROUTE, "numbers": digits[2:], "message": text, "flash": "0"}
    if FAST2SMS_ROUTE == "dlt":
        fields.update({"sender_id": FAST2SMS_SENDER, "message": FAST2SMS_TEMPLATE, "variables_values": text})
    req = urllib.request.Request("https://www.fast2sms.com/dev/bulkV2", data=urllib.parse.urlencode(fields).encode())
    req.add_header("authorization", FAST2SMS_KEY)
    with urllib.request.urlopen(req, timeout=10) as r:
        body = json.loads(r.read().decode() or "{}")
        return r.status == 200 and body.get("return") is True


def send(kind, subject, severity, msg):
    """Called when a new alert is raised. -> the notification record, or None when nothing was attempted. Never raises."""
    try:
        s = get_settings()
        if _muted[0] or not s["enabled"] or not s["phone"]:
            return None
        if s["min_severity"] == "high" and severity != "high":
            return None
        t = now()
        recent = [n for n in store.list("notifications") if t - n["ts"] < 86400]
        if any(n["key"] == "%s|%s" % (kind, subject) and t - n["ts"] < REPEAT_SECONDS for n in recent):
            return None
        rec = {"ts": t, "key": "%s|%s" % (kind, subject), "kind": kind, "subject": subject, "severity": severity,
               "to": mask(s["phone"]), "channel": PROVIDER, "text": build_text(kind, subject, msg, s["lang"])}
        if sum(1 for n in recent if n.get("status") == "sent") >= DAILY_CAP:
            rec["status"] = "skipped: daily limit"
        elif PROVIDER in ("twilio", "fast2sms") and _configured():
            try:
                fn = _send_twilio if PROVIDER == "twilio" else _send_fast2sms
                rec["status"] = "sent" if fn(s["phone"], rec["text"]) else "failed"
            except Exception as e:
                logging.getLogger("gomitra").warning("sms failed: %s", e)
                rec["status"] = "failed"
        else:
            rec["status"] = "logged, not sent (no SMS provider configured)"
        store.put("notifications", uuid.uuid4().hex, rec)
        return rec
    except Exception:
        logging.getLogger("gomitra").exception("notify failed")
        return None


def recent(limit=20):
    return sorted(store.list("notifications"), key=lambda n: -n["ts"])[:limit]
