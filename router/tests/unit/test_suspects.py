"""domain/suspects.py: which cow should the farmer check first, and has one been down for hours?"""
from gomitra.domain import suspects

NOW = 1_000_000.0


def seen(labels, gap=7200, start=600):
    """Sightings newest first: the newest is `start` seconds old, then every `gap` seconds."""
    return [{"ts": NOW - start - i * gap, "label": lab} for i, lab in enumerate(labels)]


def test_streak_counts_back_from_the_newest_sighting_until_she_stood():
    st = suspects.lying_streak(seen(["lying", "lying", "sitting", "lying", "standing", "lying"]), NOW)
    assert st == {"hours": 6.0, "n": 4, "fresh": True}
    assert suspects.down_flag(st)


def test_a_cow_seen_standing_most_recently_has_no_streak():
    assert suspects.lying_streak(seen(["standing", "lying", "lying", "lying"]), NOW)["n"] == 0


def test_down_needs_hours_sightings_and_a_recent_view():
    assert not suspects.down_flag(suspects.lying_streak(seen(["lying"] * 3, gap=1800), NOW))      # only 1 hour
    assert not suspects.down_flag(suspects.lying_streak(seen(["lying"] * 2), NOW))                 # too few sightings
    stale = [{"ts": NOW - 5 * 3600, "label": "lying"}] * 4
    assert not suspects.lying_streak(stale, NOW)["fresh"] and not suspects.down_flag(suspects.lying_streak(stale, NOW))
    assert suspects.lying_streak([], NOW) == {"hours": 0.0, "n": 0, "fresh": False}


def cow(cid, name, labels, **kw):
    return suspects.score_cow(dict(id=cid, name=name, **kw), seen(labels), None, None, NOW)


def test_the_cow_that_stands_out_is_named():
    r = suspects.rank([cow("a", "Alpha", ["lying"] * 4), cow("b", "Beta", ["standing"] * 4), cow("c", "Gamma", ["standing"] * 4)])
    assert r["stands_out"] and r["ranked"][0]["name"] == "Alpha"
    assert "Alpha" in suspects.lines(r)["en"] and "Alpha" in suspects.lines(r)["hi"] and "Alpha" in suspects.lines(r)["te"]


def test_two_similar_cows_means_it_cannot_tell():
    r = suspects.rank([cow("a", "Alpha", ["lying"] * 2), cow("b", "Beta", ["lying"] * 2)])
    assert not r["stands_out"]
    assert "could not tell" in suspects.lines(r)["en"]
    assert "Alpha" in suspects.lines(r)["en"] and "Beta" in suspects.lines(r)["en"]


def test_nothing_unusual_says_so():
    r = suspects.rank([cow("a", "Alpha", ["standing"] * 4), cow("b", "Beta", ["standing"] * 4)])
    assert "No cow looks unusual" in suspects.lines(r)["en"]
    assert suspects.lines(suspects.rank([]))["en"] == suspects.NOTHING["en"]


def test_rest_trend_gait_and_existing_alert_add_to_the_score():
    base = suspects.score_cow(dict(id="a", name="A"), seen(["standing"] * 3), None, None, NOW)["score"]
    with_rest = suspects.score_cow(dict(id="a", name="A"), seen(["standing"] * 3), {"flag": True, "today": .75, "base": .4}, None, NOW)
    with_gait = suspects.score_cow(dict(id="a", name="A"), seen(["standing"] * 3), None, {"scores": [1, 2, 3]}, NOW)
    with_alert = suspects.score_cow(dict(id="a", name="A", alert=True, kind="fmd"), seen(["standing"] * 3), None, None, NOW)
    assert base == 0 and with_rest["score"] > 0 and with_gait["score"] > 0 and with_alert["score"] > 0
    assert any(k == "rest_day" for k, _ in with_rest["reasons"]) and any(k == "gait" for k, _ in with_gait["reasons"])


def test_every_reason_is_translated():
    for key, text in suspects.REASON.items():
        assert set(text) == {"en", "hi", "te"}, key
    for table in (suspects.FIRST, suspects.UNSURE, suspects.NOTHING, suspects.ALSO_CHEWING):
        assert set(table) == {"en", "hi", "te"}
