"""Habit trends, "down for hours", the group chewing alert, the vet report, and the demo data (all without the models)."""


def test_the_simulated_week_raises_the_expected_alerts(client, seeded):
    assert seeded["cows"]["tulasi"]["flag"] and not seeded["cows"]["kamala"]["flag"] and not seeded["cows"]["lakshmi"]["flag"]
    assert seeded["eating"]["flag"] and seeded["eating"]["ratio"] <= 0.6
    t = client.get("/api/cows/tulasi").json()
    assert t["alert"] and t["kind"] == "down" and t["severity"] == "high"
    assert set(t["msg"]) == {"en", "hi", "te"} and "chewing" in t["msg"]["en"]["text"]          # the sound agrees, so it says so


def test_trends_endpoint(client, seeded):
    tr = client.get("/api/cows/tulasi/trends").json()
    assert tr["rest"]["flag"] and tr["streak"]["hours"] >= 4 and tr["streak"]["fresh"]
    assert not client.get("/api/cows/kamala/trends").json()["rest"]["flag"]
    assert client.get("/api/cows/nandini/trends").json()["gait"]["flag"]                        # 1, 1, 1, 2, 2 is rising


def test_group_chewing_and_the_cow_to_check_first(client, seeded):
    s = client.get("/api/sounds", params={"camera": "North field camera"}).json()
    assert s["trend"]["flag"] and s["meals"] >= 2
    assert "Tulasi" in s["check_first"]["en"] and s["check_first_stands_out"] is True
    alerts = [a for a in client.get("/api/alerts").json() if a["kind"] == "eating"]
    assert len(alerts) == 1 and alerts[0]["suspects"][0]["name"] == "Tulasi"
    assert alerts[0]["msg"]["te"]["advice"].endswith(alerts[0]["check_first"]["te"])
    client.get("/api/sounds", params={"camera": "North field camera"})
    assert len([a for a in client.get("/api/alerts").json() if a["kind"] == "eating"]) == 1       # no duplicate alert


def test_resolving_an_alert_hides_it(client, seeded):
    aid = client.get("/api/alerts").json()[0]["id"]
    client.post(f"/api/alerts/{aid}/resolve")
    assert aid not in [a["id"] for a in client.get("/api/alerts").json()]


def test_building_the_history_again_replaces_its_own_data(client, admin, seeded):
    again = client.post("/api/demo/history", headers=admin).json()
    assert again["posture_sightings"] == seeded["posture_sightings"] and again["chew_clips"] == seeded["chew_clips"]
    assert len([a for a in client.get("/api/alerts").json() if a["kind"] == "eating"]) == 1


def test_the_vet_report_uses_the_stored_facts_and_a_plain_note_without_gemini(client, seeded):
    r = client.get("/api/cows/tulasi/report", params={"lang": "te"}).json()
    f = r["facts"]
    assert r["source"] == "template" and "75%" in r["note"] and "39%" in r["note"]
    assert f["resting"]["clearly_higher"] and f["current_alert"]["what"].startswith("lying down") and f["group_chewing"]["clearly_lower"]
    assert isinstance(r["trace"], list)          # steps are measured per call; the in-memory store and an unreachable Gemini add none
    assert client.get("/api/cows/tulasi/report", params={"lang": "xx"}).status_code == 400


# ---- auto-refresh and reset
def test_opening_the_app_rebuilds_the_week_when_it_is_missing_or_old(client, admin):
    import time
    from gomitra.context import store
    from gomitra.services import demo
    client.post("/api/demo/seed", headers=admin)
    assert client.post("/api/warmup", headers={"x-forwarded-for": "5.5.5.5"}).json().get("demo_refreshed") is True      # missing
    assert client.get("/api/cows/tulasi/trends").json()["rest"]["flag"]
    demo._hist_check["at"] = 0.0
    assert "demo_refreshed" not in client.post("/api/warmup", headers={"x-forwarded-for": "5.5.5.5"}).json()           # fresh
    store.put("meta", "demo_history", {"ts": time.time() - 2 * 3600}); demo._hist_check["at"] = 0.0
    assert client.post("/api/warmup", headers={"x-forwarded-for": "5.5.5.5"}).json().get("demo_refreshed") is True      # older than 90 minutes


def test_auto_refresh_can_be_switched_off(client, admin, monkeypatch):
    from gomitra import config
    monkeypatch.setattr(config, "AUTO_DEMO", False)
    client.post("/api/demo/seed", headers=admin)
    assert "demo_refreshed" not in client.post("/api/warmup").json()


def test_reset_returns_the_demo_to_a_clean_state(client, admin, seeded):
    from gomitra.context import store
    store.put("cows", "visitor-0999", {"name": "Visitor", "tag": "0999", "alert": True, "kind": "lumpy", "history": [], "last_seen": 1.0})
    store.put("observations", "o1", {"cow_id": "gauri", "ts": 1.0, "kind": "lumpy"})
    store.update("cows", "gauri", {"alert": True, "kind": "lumpy", "signals": {"skin": "check"}, "history": ["lumpy"]})
    r = client.post("/api/demo/reset", headers=admin).json()
    assert r["cows_removed"] == 1 and client.get("/api/cows/visitor-0999").status_code == 404
    g = client.get("/api/cows/gauri").json()
    assert not g["alert"] and g["signals"] == {} and store.list("observations") == [] and len(client.get("/api/cows").json()) == 12
    assert client.get("/api/cows/tulasi").json()["alert"] and r["history"]["eating"]["flag"]          # ready to show again
    assert len([a for a in client.get("/api/alerts").json() if a["kind"] == "eating"]) == 1


def test_reset_can_keep_the_cows_that_were_added(client, admin, seeded):
    from gomitra.context import store
    store.put("cows", "visitor-0999", {"name": "Visitor", "tag": "0999", "alert": False, "history": [], "last_seen": 1.0})
    assert client.post("/api/demo/reset", params={"keep_cows": "true"}, headers=admin).json()["cows_removed"] == 0
    assert client.get("/api/cows/visitor-0999").status_code == 200
