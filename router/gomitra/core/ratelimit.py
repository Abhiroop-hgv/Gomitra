"""Per-visitor rate limit: a sliding one-minute window per (visitor address, kind of call).

Counts live in this instance's memory, so it is a brake against runaway cost, not a hard limit. Pure logic (no web framework).
"""
import time


def client_ip(forwarded_for: str, peer: str = "?") -> str:
    """Cloud Run appends the real client address to the end of X-Forwarded-For, so the last entry cannot be forged."""
    return forwarded_for.split(",")[-1].strip() if forwarded_for else (peer or "?")


class RateLimiter:
    def __init__(self, limits, window_s=60, max_keys=5000, clock=time.time):
        self.limits, self.window, self.max_keys, self.clock = limits, window_s, max_keys, clock
        self._hits = {}

    def rule_for(self, path: str, method: str):
        """-> (key, cap) of the first rule that matches this request, or None."""
        for key, cap in self.limits:
            matches = path.endswith(key) if key == "/report" else path.startswith(key)
            if matches and (key != "/api/cows" or method == "POST"):
                return key, cap
        return None

    def allow(self, ip: str, path: str, method: str) -> bool:
        """Count this request and say whether it is within the allowance."""
        rule = self.rule_for(path, method)
        if rule is None:
            return True
        key, cap = rule
        t = self.clock()
        bucket = self._hits.setdefault((ip, key), [])
        bucket[:] = [x for x in bucket if t - x < self.window]
        if len(bucket) >= cap:
            return False
        bucket.append(t)
        if len(self._hits) > self.max_keys:
            self._hits.clear()
        return True
