"""Habit trends: is this cow resting, walking or (as a group) chewing differently from her own recent normal?

Rolling 24-hour windows are used, so "today" always means the last 24 hours. Window 0 is the latest, windows 1..7 are the
week before and form the baseline. All thresholds are starting points and need tuning on real farm data.
"""
DAY = 86400
WINDOWS = 8                 # window 0 = last 24 h, 1..7 = baseline
MIN_SAMPLES = 6             # posture sightings needed in a window for it to count
MIN_BASE_WINDOWS = 3        # baseline windows needed before any trend is trusted
REST_RISE = 0.15            # resting share must be this much above her baseline ...
REST_RATIO = 1.25           # ... and at least this many times her baseline
CHEW_DROP = 0.60            # chewing at or below this share of the baseline counts as eating less
CHEW_MIN_BASE = 30.0        # minutes per day the baseline must reach before "less" means anything
RESTING = ("lying", "sitting")


def window_of(ts, now):
    """Index of the 24 h window holding ts (0 = latest), or None if older than the baseline."""
    k = int((now - ts) // DAY)
    return k if 0 <= k < WINDOWS else None


def rest_trend(entries, now):
    """entries: posture sightings {"ts","label"}. -> dict with today, base (resting shares 0-1), days, flag."""
    seen = [[0, 0] for _ in range(WINDOWS)]
    for e in entries:
        k = window_of(e["ts"], now)
        if k is not None and e.get("label") in ("standing", "sitting", "lying"):
            seen[k][0] += e["label"] in RESTING
            seen[k][1] += 1
    shares = [(r / n if n >= MIN_SAMPLES else None) for r, n in seen]
    base_list = [s for s in shares[1:] if s is not None]
    out = {"today": shares[0], "base": None, "days": len(base_list), "samples": seen[0][1], "flag": False}
    if base_list:
        out["base"] = sum(base_list) / len(base_list)
    if shares[0] is not None and len(base_list) >= MIN_BASE_WINDOWS:
        b = out["base"]
        out["flag"] = shares[0] - b >= REST_RISE and shares[0] >= REST_RATIO * b
    return out


def gait_trend(entries):
    """entries: sightings with a "gait" score 1-5 (any order). Worsening = the last three never fall, and rise by 1 or more."""
    scores = [e["gait"] for e in sorted(entries, key=lambda e: e["ts"]) if isinstance(e.get("gait"), int)]
    last = scores[-3:]
    flag = len(last) == 3 and last[0] < last[2] and last[0] <= last[1] <= last[2] and last[2] >= 2
    return {"scores": scores[-6:], "flag": flag}


def chew_minutes(events, start, end):
    """events: audio events with a "chew" label. -> (minutes, meals) in [start, end); meals split at 5 minute gaps."""
    ts = sorted(e["ts"] for e in events if e.get("chew") and start <= e["ts"] < end)
    meals, last = [], None
    for t in ts:
        if last is None or t - last > 300:
            meals.append([t, t])
        else:
            meals[-1][1] = t
        last = t
    return round(sum(b - a for a, b in meals) / 60, 1), len(meals)


def eat_trend(events, now):
    """Group chewing in the last 24 h against the previous days. -> dict with today, base (minutes), days, ratio, flag."""
    mins = [chew_minutes(events, now - (k + 1) * DAY, now - k * DAY)[0] for k in range(WINDOWS)]
    base_list = [m for m in mins[1:] if m > 0]
    out = {"today": mins[0], "base": None, "days": len(base_list), "ratio": None, "flag": False}
    if base_list:
        out["base"] = round(sum(base_list) / len(base_list), 1)
        out["ratio"] = round(mins[0] / out["base"], 2)
    if len(base_list) >= MIN_BASE_WINDOWS and out["base"] >= CHEW_MIN_BASE:
        out["flag"] = mins[0] <= CHEW_DROP * out["base"]
    return out
