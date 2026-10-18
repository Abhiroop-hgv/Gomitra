"""services/report.py: the vet handover note is built from stored facts; Gemini only words it."""
from gomitra.services import report

NOW = 1_800_000_000.0
COW = {"name": "Tulasi", "tag": "0439", "breed": "Holstein-Friesian cross", "age": "4 years", "camera": "North field camera",
       "alert": True, "kind": "down", "severity": "high", "last_seen": NOW - 60, "gait_score": 2,
       "signals": {"walking": "watch", "resting": "lying"}}
REST = {"today": 0.75, "base": 0.39, "days": 7, "flag": True}
GAIT = {"scores": [1, 1, 2], "flag": True}
EAT = {"today": 40.0, "base": 88.0, "flag": True}


def facts(**kw):
    args = dict(cow=COW, observations=[], rest=REST, gait=GAIT, eating=EAT, now=NOW)
    args.update(kw)
    return report.build_facts(args["cow"], args["observations"], args["rest"], args["gait"], args["eating"], args["now"])


def test_facts_carry_the_cow_the_alert_and_the_trends():
    f = facts()
    assert f["cow"]["name"] == "Tulasi" and f["current_alert"]["what"].startswith("lying down")
    assert f["resting"]["share_last_24h_percent"] == 75 and f["resting"]["usual_percent"] == 39 and f["resting"]["clearly_higher"]
    assert f["walking"]["recent_scores"] == [1, 1, 2] and f["walking"]["scores_rising"]
    assert f["group_chewing"]["clearly_lower"] and "group" in f["group_chewing"]["note"]


def test_skin_checks_are_counted_over_the_last_14_days_only():
    obs = [{"ts": NOW - 3600, "kind": "lumpy", "p": 0.9}, {"ts": NOW - 7200, "kind": "ok"}, {"ts": NOW - 30 * 86400, "kind": "fmd"}]
    s = facts(observations=obs)["skin_checks_14_days"]
    assert s["total"] == 2 and s["by_result"] == {"ok": 1, "lumpy": 1} and s["last_finding"]["result"] == "lumpy"


def test_no_alert_and_no_data_are_handled():
    f = facts(cow=dict(COW, alert=False, kind=None), rest=None, gait=None, eating=None)
    assert f["current_alert"] is None and f["resting"]["latest_posture"] == "lying" and f["group_chewing"] is None


def test_the_plain_note_uses_only_the_facts_and_is_not_a_diagnosis():
    note = report.plain_note(facts())
    assert "Tulasi" in note and "75%" in note and "39%" in note and "40.0" in note
    assert note.endswith("not a diagnosis.")


def test_compose_falls_back_to_the_plain_note_without_gemini():
    note, source = report.compose(facts(), "te")
    assert source == "template" and "Tulasi" in note
