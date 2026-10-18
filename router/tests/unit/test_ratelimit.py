"""core/ratelimit.py: per-visitor sliding one-minute allowance."""
from gomitra.core.ratelimit import RateLimiter, client_ip


class Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


def limiter(clock=None, **kw):
    return RateLimiter([("/api/posture", 3), ("/report", 2), ("/api/cows", 2)], clock=clock or Clock(), **kw)


def test_within_the_allowance_then_blocked():
    lim = limiter()
    assert [lim.allow("1.1.1.1", "/api/posture", "POST") for _ in range(5)] == [True, True, True, False, False]


def test_each_visitor_has_their_own_allowance():
    lim = limiter()
    for _ in range(3):
        lim.allow("1.1.1.1", "/api/posture", "POST")
    assert not lim.allow("1.1.1.1", "/api/posture", "POST") and lim.allow("2.2.2.2", "/api/posture", "POST")


def test_the_allowance_comes_back_after_a_minute():
    clock = Clock(); lim = limiter(clock)
    for _ in range(3):
        lim.allow("a", "/api/posture", "POST")
    assert not lim.allow("a", "/api/posture", "POST")
    clock.t += 61
    assert lim.allow("a", "/api/posture", "POST")


def test_paths_without_a_rule_are_never_limited():
    lim = limiter()
    assert all(lim.allow("a", "/api/status", "GET") for _ in range(100))


def test_report_matches_by_suffix_and_cows_only_on_post():
    lim = limiter()
    assert lim.rule_for("/api/cows/tulasi/report", "GET") == ("/report", 2)
    assert lim.rule_for("/api/cows", "GET") is None and lim.rule_for("/api/cows", "POST") == ("/api/cows", 2)


def test_the_last_forwarded_address_is_the_visitor():
    assert client_ip("9.9.9.9, 2.2.2.2") == "2.2.2.2"          # a forged first entry cannot hide the real address
    assert client_ip("", "10.0.0.5") == "10.0.0.5" and client_ip("") == "?"


def test_memory_is_bounded():
    lim = limiter(max_keys=3)
    for i in range(10):
        lim.allow(f"ip{i}", "/api/posture", "POST")
    assert len(lim._hits) <= 4
