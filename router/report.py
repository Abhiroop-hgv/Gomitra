"""Vet handover report: what the system saw about one cow, as facts plus a short note a vet can read in a minute.

The facts come from Firestore (never from Gemini). Gemini only turns them into a readable note; if it fails, a plain
note is built from the same facts. The report never names a disease as a diagnosis.
"""
import datetime
import json
import logging

import gmtrace as trace
import messages

IST = datetime.timezone(datetime.timedelta(hours=5, minutes=30))
KIND_WORDS = {"lumpy": "skin lumps (possible lumpy skin disease)", "fmd": "mouth/foot signs (possible foot-and-mouth disease)",
              "limp": "uneven walking (possible lameness)", "rest": "resting much more than her own usual", "down": "lying down for hours without standing",
              "distress": "loud distress-like call nearby"}
LANG_NAMES = {"en": "English", "hi": "Hindi (Devanagari)", "te": "Telugu (Telugu script)"}


def day(ts):
    return datetime.datetime.fromtimestamp(ts, IST).strftime("%d %b %Y %H:%M")


def build_facts(cow, observations, rest, gait, eating, now):
    """-> dict of plain facts (all from stored data)."""
    obs = sorted([o for o in observations if now - o["ts"] <= 14 * 86400], key=lambda o: o["ts"])
    counts = {}
    for o in obs:
        counts[o["kind"]] = counts.get(o["kind"], 0) + 1
    findings = [o for o in obs if o["kind"] != "ok"]
    sig = cow.get("signals") or {}
    f = {"cow": {k: cow.get(k) for k in ("name", "tag", "breed", "age", "camera")},
         "report_time": day(now),
         "current_alert": ({"what": KIND_WORDS.get(cow.get("kind"), cow.get("kind")), "severity": cow.get("severity"),
                            "last_update": day(cow["last_seen"])} if cow.get("alert") else None),
         "skin_checks_14_days": {"total": len(obs), "by_result": counts,
                                 "last_finding": ({"result": findings[-1]["kind"], "probability": findings[-1].get("p"),
                                                   "when": day(findings[-1]["ts"])} if findings else None)},
         "walking": {"latest_score_1_to_5": cow.get("gait_score"), "recent_scores": (gait or {}).get("scores") or [],
                     "scores_rising": bool((gait or {}).get("flag")), "state": sig.get("walking")},
         "resting": None, "group_chewing": None}
    if rest and rest.get("today") is not None and rest.get("base") is not None:
        f["resting"] = {"share_last_24h_percent": round(rest["today"] * 100), "usual_percent": round(rest["base"] * 100),
                        "days_in_baseline": rest["days"], "clearly_higher": bool(rest["flag"]), "latest_posture": sig.get("resting")}
    elif sig.get("resting"):
        f["resting"] = {"latest_posture": sig["resting"], "note": "not enough days of data for a trend"}
    if eating and eating.get("base") is not None:
        f["group_chewing"] = {"minutes_last_24h": eating["today"], "usual_minutes": eating["base"],
                              "clearly_lower": bool(eating["flag"]), "note": "per camera group, not per cow"}
    return f


def plain_note(f):
    """English note built only from the facts (used when Gemini is unavailable)."""
    c = f["cow"]
    lines = [f"{c['name']} (ear tag {c['tag']}, {c.get('breed') or 'breed not recorded'}, {c.get('age') or 'age not recorded'})."]
    a = f["current_alert"]
    lines.append(f"Current alert: {a['what']}, severity {a['severity']}, last updated {a['last_update']}." if a else "No alert is open now.")
    s = f["skin_checks_14_days"]
    if s["total"]:
        lines.append(f"Skin checks in the last 14 days: {s['total']} ({', '.join(f'{k}: {v}' for k, v in s['by_result'].items())}).")
    w = f["walking"]
    if w["recent_scores"]:
        lines.append("Walking scores (1 normal to 5 severe), oldest first: " + ", ".join(map(str, w["recent_scores"])) + ".")
    r = f["resting"]
    if r and "share_last_24h_percent" in r:
        lines.append(f"Resting {r['share_last_24h_percent']}% of sightings in the last 24 hours against her usual {r['usual_percent']}%.")
    g = f["group_chewing"]
    if g:
        lines.append(f"Group chewing in the last 24 hours: {g['minutes_last_24h']} min against a usual {g['usual_minutes']} min (whole camera group).")
    lines.append("This is a camera screening summary, not a diagnosis.")
    return " ".join(lines)


def compose(f, lang="en"):
    """-> (note text, "gemini" | "template")."""
    base = plain_note(f)
    try:
        client, types = messages._gemini_client()
        prompt = f"""You write a short handover note for a veterinarian from a cattle-monitoring system.
Use ONLY the facts below. Do not invent any value, date, treatment or history. Do not state a diagnosis; say "possible" for suspected diseases.
Write in {LANG_NAMES.get(lang, 'English')}, plain words, at most 120 words, in this order:
1) who the cow is, 2) why the farmer is calling, 3) what the camera saw (with dates and numbers from the facts), 4) what is NOT known (cause, fever, appetite, milk yield, treatment given) so the vet can ask.
No headings, no bullet symbols; short paragraphs only. Mention that chewing is a group figure if you use it.
Facts (JSON): {json.dumps(f, ensure_ascii=False)}"""
        with trace.step("Gemini on Vertex AI", f"{messages.GEMINI_MODEL}, vet handover note"):
            r = client.models.generate_content(model=messages.GEMINI_MODEL, contents=prompt,
                                               config=types.GenerateContentConfig(temperature=0.2))
        text = (r.text or "").strip()
        if len(text) < 40:
            raise ValueError("empty note")
        return text, "gemini"
    except Exception:
        logging.getLogger("gomitra").exception("gemini vet report failed, using plain note")
        return base, "template"
