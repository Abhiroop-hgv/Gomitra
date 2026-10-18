"""domain/trends.py: is she resting, walking or (as a group) chewing differently from her own recent normal?"""
from gomitra.domain import trends

NOW = 1_000_000.0
DAY = 86400


def sightings(per_day, resting):
    """per_day / resting: counts per 24 h window, window 0 (the latest) first."""
    out = []
    for k, (n, r) in enumerate(zip(per_day, resting)):
        out += [{"ts": NOW - k * DAY - i * 3000, "label": "lying" if i < r else "standing"} for i in range(n)]
    return out


def test_clear_rise_over_her_own_week_flags():
    t = trends.rest_trend(sightings([12] * 8, [9] + [5] * 7), NOW)
    assert t["flag"] and t["today"] == 0.75 and abs(t["base"] - 5 / 12) < 1e-9 and t["days"] == 7


def test_small_change_does_not_flag():
    assert not trends.rest_trend(sightings([12] * 8, [6] + [5] * 7), NOW)["flag"]


def test_a_cow_that_always_rests_a_lot_is_not_flagged():
    assert not trends.rest_trend(sightings([12] * 8, [9] + [8] * 7), NOW)["flag"]


def test_needs_enough_baseline_days_and_enough_sightings_today():
    assert not trends.rest_trend(sightings([12] * 3, [9, 5, 5]), NOW)["flag"]                    # only 2 baseline days
    assert not trends.rest_trend(sightings([4] + [12] * 7, [4] + [5] * 7), NOW)["flag"]          # 4 sightings today


def test_sitting_counts_as_resting_and_unknown_labels_are_ignored():
    es = [{"ts": NOW - 100, "label": "sitting"}] * 6 + [{"ts": NOW - 100, "label": "unknown"}] * 20
    assert trends.rest_trend(es, NOW)["today"] == 1.0


def test_gait_trend_flags_only_a_worsening_pattern():
    g = lambda scores: trends.gait_trend([{"ts": i, "gait": s} for i, s in enumerate(scores)])
    assert g([1, 1, 2, 2])["flag"] and g([1, 2, 3])["flag"]
    assert not g([1, 1, 1])["flag"] and not g([3, 2, 1])["flag"] and not g([2, 2, 2])["flag"] and not g([1, 2])["flag"]
    assert g([1, 1, 1, 2, 2, 3, 3, 4])["scores"] == [1, 1, 2, 2, 3, 3, 4][-6:]          # only the latest six are kept


def test_meals_split_at_five_minute_gaps():
    clips = [{"ts": NOW - 7200 + j * 120, "chew": "chew"} for j in range(11)]            # one 20-minute meal
    clips += [{"ts": NOW - 3600 + j * 120, "chew": "chew"} for j in range(6)]            # a second, 10 minutes
    assert trends.chew_minutes(clips, NOW - DAY, NOW) == (30.0, 2)
    assert trends.chew_minutes([], NOW - DAY, NOW) == (0.0, 0)
    assert trends.chew_minutes([{"ts": NOW - 10, "chew": None}], NOW - DAY, NOW) == (0.0, 0)   # no chewing label


def _meals(day, n_meals):
    out = []
    for m in range(n_meals):
        out += [{"ts": NOW - day * DAY - 20 * 3600 + m * 4 * 3600 + j * 120, "chew": "chew"} for j in range(12)]
    return out


def test_group_chewing_far_below_usual_flags():
    events = _meals(0, 2)
    for d in range(1, 8):
        events += _meals(d, 4)
    t = trends.eat_trend(events, NOW)
    assert t["flag"] and t["ratio"] <= 0.6 and t["days"] == 7


def test_group_chewing_close_to_usual_does_not_flag():
    events = sum((_meals(d, 4) for d in range(8)), [])
    assert not trends.eat_trend(events, NOW)["flag"]


def test_no_baseline_means_no_flag():
    t = trends.eat_trend(_meals(0, 1), NOW)
    assert not t["flag"] and t["base"] is None
