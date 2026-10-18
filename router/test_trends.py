"""Offline test of the habit trends (no models, no cloud). python test_trends.py"""
import os
os.environ.update(STORE="memory", INFER_BACKEND="local", EMBED_BACKEND="fake", ADMIN_KEY="k",
                  SERVING_DIR=os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "serving"))
import time
from fastapi.testclient import TestClient
import main
import trends

# ---- pure rules
now = 1_000_000.0
def sights(per_day, rested):
    """per_day: list (window 0 first) of sighting counts; rested: resting counts"""
    out = []
    for k, (n, r) in enumerate(zip(per_day, rested)):
        for i in range(n):
            out.append({"ts": now - k * 86400 - i * 3000, "label": "lying" if i < r else "standing"})
    return out

t = trends.rest_trend(sights([12] * 8, [9] + [5] * 7), now)
assert t["flag"] and abs(t["today"] - .75) < 1e-9 and abs(t["base"] - 5 / 12) < 1e-9, t
assert not trends.rest_trend(sights([12] * 8, [6] + [5] * 7), now)["flag"]            # small change: no alert
assert not trends.rest_trend(sights([12] * 8, [9, 5, 5], ), now)["flag"]              # too few baseline days
assert not trends.rest_trend(sights([4] + [12] * 7, [4] + [5] * 7), now)["flag"]      # too few sightings today
assert not trends.rest_trend(sights([12] * 8, [9] + [8] * 7), now)["flag"]            # a cow that always rests a lot
assert trends.gait_trend([{"ts": i, "gait": g} for i, g in enumerate([1, 1, 2, 2])])["flag"]
assert not trends.gait_trend([{"ts": i, "gait": g} for i, g in enumerate([1, 1, 1])])["flag"]
assert not trends.gait_trend([{"ts": i, "gait": g} for i, g in enumerate([3, 2, 1])])["flag"]
ev = [{"ts": now - 3600 + j * 120, "chew": "chewing"} for j in range(11)]                # one 20 minute meal
assert trends.chew_minutes(ev, now - 86400, now) == (20.0, 1)
# ---- suspects: lying streak, down flag, ranking
import suspects
sg = lambda labels, gap=7200: [{"ts": now - 600 - i * gap, "label": l} for i, l in enumerate(labels)]      # newest first
st = suspects.lying_streak(sg(["lying", "lying", "sitting", "lying", "standing", "lying"]), now)
assert st == {"hours": 6.0, "n": 4, "fresh": True} and suspects.down_flag(st), st
assert suspects.lying_streak(sg(["standing", "lying", "lying", "lying", "lying"]), now)["n"] == 0                      # stood most recently
assert not suspects.down_flag(suspects.lying_streak(sg(["lying", "lying", "lying"], gap=1800), now))                  # only 1 hour
assert not suspects.down_flag(suspects.lying_streak(sg(["lying"] * 5, gap=7200)[:2], now))                            # too few sightings
assert not suspects.lying_streak([{"ts": now - 5 * 3600, "label": "lying"}] * 4, now)["fresh"]                         # not seen recently
mk = lambda cid, name, labels, **kw: suspects.score_cow(dict(id=cid, name=name, **kw), sg(labels), None, None, now)
r = suspects.rank([mk("a", "Alpha", ["lying"] * 4), mk("b", "Beta", ["standing"] * 4), mk("c", "Gamma", ["standing"] * 4)])
assert r["stands_out"] and r["ranked"][0]["name"] == "Alpha"
r2 = suspects.rank([mk("a", "Alpha", ["lying"] * 2), mk("b", "Beta", ["lying"] * 2)])
assert not r2["stands_out"] and "could not tell" in suspects.lines(r2)["en"].lower() or "could not tell" in suspects.lines(r2)["en"].lower()
r3 = suspects.rank([mk("a", "Alpha", ["standing"] * 4), mk("b", "Beta", ["standing"] * 4)])
assert "No cow looks unusual" in suspects.lines(r3)["en"]
print("rules ok")

# ---- through the API
c = TestClient(main.app)
H = {"x-admin-key": "k"}
c.post("/api/demo/seed", headers=H)
r = c.post("/api/demo/history", headers=H).json()
print(r)
assert r["cows"]["tulasi"]["flag"] and not r["cows"]["kamala"]["flag"] and not r["cows"]["lakshmi"]["flag"], r
assert r["eating"]["flag"] and r["eating"]["ratio"] <= 0.6, r["eating"]
tul = c.get("/api/cows/tulasi").json()
assert tul["alert"] and tul["kind"] == "down" and tul["severity"] is not None and set(tul["msg"]) == {"en", "hi", "te"}, tul
assert "chewing" in tul["msg"]["en"]["text"], tul["msg"]["en"]["text"]          # sound agrees: the group-chewing line is added
tr = c.get("/api/cows/tulasi/trends").json()
assert tr["rest"]["flag"] and not c.get("/api/cows/kamala/trends").json()["rest"]["flag"]
assert c.get("/api/cows/nandini/trends").json()["gait"]["flag"]
s = c.get("/api/sounds", params={"camera": main.HISTORY_CAMERA}).json()
assert s["trend"]["flag"] and s["clips"] >= 22 and s["meals"] == 2, s
al = [a for a in c.get("/api/alerts").json() if a["kind"] == "eating"]
assert len(al) == 1, al
# the sound alert names the cow to check first (Tulasi: down for hours, resting far above usual), in all three languages
assert al[0]["stands_out"] and al[0]["suspects"][0]["name"] == "Tulasi", al[0]["suspects"]
assert "Tulasi" in al[0]["check_first"]["en"] and "Tulasi" in al[0]["check_first"]["hi"] and "Tulasi" in al[0]["check_first"]["te"]
assert al[0]["msg"]["te"]["advice"].endswith(al[0]["check_first"]["te"]), "the line is part of the advice"
assert s["check_first"]["en"] == al[0]["check_first"]["en"] and s["check_first_stands_out"] is True, s
assert c.get("/api/cows/tulasi/trends").json()["streak"]["hours"] >= 4
c.get("/api/sounds", params={"camera": main.HISTORY_CAMERA})
assert len([a for a in c.get("/api/alerts").json() if a["kind"] == "eating"]) == 1       # no duplicate alert
# a distress call: the alert tells the farmer which cow to check first
import base64 as _b64
wav = _b64.b64encode(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "static", "samples", "sound_distress.wav"), "rb").read()).decode()
d = c.post("/api/audio", json={"audio": wav, "camera": main.HISTORY_CAMERA, "immediate": True}).json()
assert d["alert"] and "Tulasi" in d["alert"]["check_first"]["en"] and d["alert"]["stands_out"], d["alert"]
assert d["alert"]["msg"]["hi"]["advice"].endswith(d["alert"]["check_first"]["hi"])
# repeating the seed replaces its own data and keeps one alert
r2 = c.post("/api/demo/history", headers=H).json()
assert r2["posture_sightings"] == r["posture_sightings"] and r2["chew_clips"] == r["chew_clips"]
assert len([a for a in c.get("/api/alerts").json() if a["kind"] == "eating"]) == 1
assert c.post("/api/demo/history").status_code == 403
# vet report: facts come from stored data; without Gemini the plain note is used
rp = c.get("/api/cows/tulasi/report").json()
assert rp["source"] == "template" and "75%" in rp["note"] and "39%" in rp["note"], rp
assert rp["facts"]["resting"]["clearly_higher"] and rp["facts"]["current_alert"]["what"].startswith("lying down")
assert c.get("/api/cows/nandini/report", params={"lang": "te"}).status_code == 200
assert c.get("/api/cows/tulasi/report", params={"lang": "xx"}).status_code == 400
assert c.get("/api/cows/nobody/report").status_code == 404
print(rp["note"])
# abuse guard: 8 posture calls a minute per visitor, then 429; another visitor and the admin key are not blocked
codes = [c.post("/api/posture", json={"images": []}, headers={"x-forwarded-for": "1.1.1.1"}).status_code for _ in range(22)]
assert codes[:20] == [400] * 20 and codes[20:] == [429, 429], codes
assert c.post("/api/posture", json={"images": []}, headers={"x-forwarded-for": "2.2.2.2"}).status_code == 400
assert c.post("/api/posture", json={"images": []}, headers={"x-forwarded-for": "1.1.1.1", "x-admin-key": "k"}).status_code == 400
assert c.post("/api/posture", json={"images": []}, headers={"x-forwarded-for": "9.9.9.9, 2.2.2.2"}).status_code == 400    # last entry is the real visitor
r = c.get("/health"); assert r.headers["x-content-type-options"] == "nosniff"
assert c.post("/api/warmup").json() == {"started": False}      # no pose service configured offline
# ---- auto-refresh: opening the app rebuilds the simulated week when it is missing or old, and not otherwise
main.store.delete_many("meta", ["demo_history"]); main._hist_check["at"] = 0.0
main.store.delete_many("posture_log", [d["id"] for d in main.store.list("posture_log")])         # as if the data had gone
assert c.get("/api/cows/tulasi/trends").json()["rest"]["today"] is None
assert c.post("/api/warmup", headers={"x-forwarded-for": "5.5.5.5"}).json().get("demo_refreshed") is True
assert c.get("/api/cows/tulasi/trends").json()["rest"]["flag"]
stamp = main.store.get("meta", "demo_history")["ts"]; main._hist_check["at"] = 0.0
assert "demo_refreshed" not in c.post("/api/warmup", headers={"x-forwarded-for": "5.5.5.5"}).json()    # fresh: left alone
assert main.store.get("meta", "demo_history")["ts"] == stamp
main.store.put("meta", "demo_history", {"ts": time.time() - 9 * 3600}); main._hist_check["at"] = 0.0
assert c.post("/api/warmup", headers={"x-forwarded-for": "5.5.5.5"}).json().get("demo_refreshed") is True   # older than 8 h

# ---- clean reset
main.store.put("cows", "visitor-0999", {"name": "Visitor", "tag": "0999", "alert": True, "kind": "lumpy", "history": [], "last_seen": 1.0})
main.store.put("observations", "o1", {"cow_id": "gauri", "ts": 1.0, "kind": "lumpy"})
main.store.update("cows", "gauri", {"alert": True, "kind": "lumpy", "signals": {"skin": "check"}, "history": ["lumpy"]})
assert c.post("/api/demo/reset").status_code == 403
r = c.post("/api/demo/reset", headers=H).json(); print({k: v for k, v in r.items() if k != "history"})
assert r["cows_removed"] == 1 and c.get("/api/cows/visitor-0999").status_code == 404
g = c.get("/api/cows/gauri").json(); assert not g["alert"] and g["signals"] == {}
assert main.store.list("observations") == [] and len(c.get("/api/cows").json()) == 12
assert c.get("/api/cows/tulasi").json()["alert"] and r["history"]["eating"]["flag"]                      # demo is back, ready to show
assert len([a for a in c.get("/api/alerts").json() if a["kind"] == "eating"]) == 1
main.store.put("cows", "visitor-0999", {"name": "Visitor", "tag": "0999", "alert": False, "history": [], "last_seen": 1.0})
assert c.post("/api/demo/reset", params={"keep_cows": "true"}, headers=H).json()["cows_removed"] == 0
assert c.get("/api/cows/visitor-0999").status_code == 200
print("api ok")
