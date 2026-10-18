"""Which cow should the farmer look at first, and has one cow been down for hours?

A microphone group cannot say which cow made a sound, so when a sound alert is raised (a distress call, or chewing far below
usual) the app looks at what the cameras saw of every cow in that group and ranks them by how inactive or odd they look.
The top cow is named only if she clearly stands out; otherwise the message says it could not tell and lists the most inactive.
This is inference by elimination, not proof, and the message says "check first", not "this cow made the sound".
Thresholds are starting points and need tuning on real farm data.
"""
RESTING = ("lying", "sitting")
FRESH_S = 3 * 3600          # a cow's latest sighting must be this recent to count as "right now"
DOWN_HOURS = 4.0            # lying at every sighting for at least this long, without a standing sighting, is "down for hours"
DOWN_MIN_SIGHTINGS = 3      # and it must be backed by at least this many sightings
STAND_OUT = 0.35            # a cow needs at least this score to be named
MARGIN = 0.15               # and must beat the next cow by this much
SOMETHING = 0.10            # below this for every cow = nothing unusual

REASON = {
    "lying_h": {"en": "lying for about {h} hours without standing", "hi": "लगभग {h} घंटे से बिना खड़े हुए लेटी है",
                "te": "నిలబడకుండా సుమారు {h} గంటలుగా పడుకుని ఉంది"},
    "rest_day": {"en": "resting {a}% of the day (usual {b}%)", "hi": "दिन का {a}% आराम (सामान्यतः {b}%)",
                 "te": "రోజులో {a}% విశ్రాంతి (మామూలుగా {b}%)"},
    "has_alert": {"en": "already has an alert", "hi": "पहले से अलर्ट है", "te": "ఇప్పటికే హెచ్చరిక ఉంది"},
    "gait": {"en": "walking score {s} of 5", "hi": "चाल का स्कोर {s}/5", "te": "నడక స్కోర్ {s}/5"},
}
FIRST = {"en": "Please check {name} first: {why}.", "hi": "कृपया पहले {name} को देखें: {why}।",
         "te": "దయచేసి ముందు {name}ను చూడండి: {why}."}
UNSURE = {"en": "I could not tell which cow it is. The most inactive right now: {names}.",
          "hi": "पता नहीं चला कि कौन सी गाय है। अभी सबसे कम सक्रिय: {names}।",
          "te": "ఏ ఆవో తెలియలేదు. ఇప్పుడు అత్యంత నిష్క్రియంగా ఉన్నవి: {names}."}
NOTHING = {"en": "No cow looks unusual on the cameras right now.", "hi": "कैमरों में अभी कोई गाय असामान्य नहीं दिखती।",
           "te": "ప్రస్తుతం కెమెరాల్లో ఏ ఆవూ అసాధారణంగా కనిపించడం లేదు."}
ALSO_CHEWING = {"en": "Group chewing is also far below usual.", "hi": "समूह का चबाना भी सामान्य से बहुत कम है।",
                "te": "సమూహం నమలడం కూడా మామూలు కంటే చాలా తక్కువగా ఉంది."}


def lying_streak(entries, now):
    """Posture sightings {"ts","label"} -> {"hours","n","fresh"}: how long she has been lying or sitting at every sighting,
    counted back from the newest one. hours = newest minus oldest sighting of that streak; 0 if she stood at the newest one."""
    es = sorted((e for e in entries if e.get("label") in ("standing",) + RESTING), key=lambda e: -e["ts"])
    if not es or now - es[0]["ts"] > FRESH_S:
        return {"hours": 0.0, "n": 0, "fresh": False}
    n, oldest = 0, es[0]["ts"]
    for e in es:
        if e["label"] not in RESTING:
            break
        n, oldest = n + 1, e["ts"]
    return {"hours": round((es[0]["ts"] - oldest) / 3600, 1), "n": n, "fresh": True}


def down_flag(streak):
    return streak["fresh"] and streak["n"] >= DOWN_MIN_SIGHTINGS and streak["hours"] >= DOWN_HOURS


def score_cow(cow, entries, rest, gait, now):
    """-> {"id","name","score","reasons":[(key, params)]}. Higher = more inactive or odd."""
    st = lying_streak(entries, now)
    s, why = 0.0, []
    if st["fresh"] and st["n"] >= 2 and st["hours"] >= 1:
        s += 0.5 * min(st["hours"] / 6.0, 1.0)
        why.append(("lying_h", {"h": int(round(st["hours"]))}))
    if rest and rest.get("flag"):
        s += 0.2
        why.append(("rest_day", {"a": round(rest["today"] * 100), "b": round(rest["base"] * 100)}))
    last = (gait or {}).get("scores", [])[-1:] or [0]
    if last[0] >= 2:
        s += 0.15 if last[0] >= 3 else 0.08
        why.append(("gait", {"s": last[0]}))
    if cow.get("alert") and cow.get("kind") in ("lumpy", "fmd", "limp", "rest", "down"):
        s += 0.15
        why.append(("has_alert", {}))
    return {"id": cow["id"], "name": cow["name"], "score": round(s, 3), "reasons": why, "seen": st["fresh"]}


def rank(scored):
    """-> {"stands_out": bool, "ranked": [scored cow, best first]}."""
    ranked = sorted(scored, key=lambda c: -c["score"])
    top = ranked[0]["score"] if ranked else 0.0
    nxt = ranked[1]["score"] if len(ranked) > 1 else 0.0
    return {"stands_out": bool(ranked) and top >= STAND_OUT and (top - nxt >= MARGIN), "ranked": ranked}


def lines(result):
    """-> {"en","hi","te"} one sentence for the alert."""
    ranked, out = result["ranked"], {}
    for lang in ("en", "hi", "te"):
        if not ranked or ranked[0]["score"] < SOMETHING:
            out[lang] = NOTHING[lang]
        elif result["stands_out"]:
            top = ranked[0]
            why = "; ".join(REASON[k][lang].format(**p) for k, p in top["reasons"]) or REASON["has_alert"][lang]
            out[lang] = FIRST[lang].format(name=top["name"], why=why)
        else:
            names = ", ".join(c["name"] for c in ranked[:3] if c["score"] >= SOMETHING)
            out[lang] = UNSURE[lang].format(names=names)
    return out
