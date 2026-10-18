"""SMS notifier: settings, repeats, daily cap, severity filter, provider failure, muting."""
import pytest

from gomitra.context import store
from gomitra.services import messages, notify

MSG = messages.template("down", "Tulasi")


@pytest.fixture
def on():
    notify.set_settings("+919876543210", "en", True, "medium")


def test_settings_validate_and_mask():
    with pytest.raises(ValueError):
        notify.set_settings("9876543210")                      # needs the + country code
    with pytest.raises(ValueError):
        notify.set_settings("+919876543210", lang="fr")
    s = notify.set_settings("+91 98765 43210", "te", True, "high")
    assert s["lang"] == "te" and "98765" not in s["phone"] and s["phone"].endswith("210")


def test_nothing_is_sent_when_off_or_without_a_phone():
    assert notify.send("down", "Tulasi", "high", MSG) is None
    notify.set_settings("", enabled=False)
    assert notify.send("down", "Tulasi", "high", MSG) is None


def test_logged_not_sent_without_a_provider(on):
    rec = notify.send("down", "Tulasi", "high", MSG)
    assert rec["status"].startswith("logged") and "Tulasi" in rec["text"] and len(rec["text"]) <= notify.MAX_CHARS
    assert "98765" not in rec["to"] and notify.recent()[0]["subject"] == "Tulasi"


def test_the_message_uses_the_chosen_language(on):
    notify.set_settings("+919876543210", "hi", True)
    assert notify.send("down", "Tulasi", "high", MSG)["text"].split(" - ")[1].startswith(MSG["hi"]["title"])


def test_same_alert_is_not_repeated_but_another_cow_is(on):
    assert notify.send("down", "Tulasi", "high", MSG)
    assert notify.send("down", "Tulasi", "high", MSG) is None
    assert notify.send("down", "Kamala", "high", MSG)
    assert notify.send("rest", "Tulasi", "medium", MSG)


def test_high_only_filter(on):
    notify.set_settings("+919876543210", "en", True, "high")
    assert notify.send("rest", "Tulasi", "medium", MSG) is None
    assert notify.send("down", "Tulasi", "high", MSG)


def test_daily_cap(on, monkeypatch):
    monkeypatch.setattr(notify, "DAILY_CAP", 2)
    monkeypatch.setattr(notify, "PROVIDER", "twilio")
    monkeypatch.setattr(notify, "TWILIO_SID", "x"), monkeypatch.setattr(notify, "TWILIO_TOKEN", "x")
    monkeypatch.setattr(notify, "TWILIO_FROM", "+1")
    monkeypatch.setattr(notify, "_send_twilio", lambda to, text: True)
    out = [notify.send("down", "Cow%d" % i, "high", MSG)["status"] for i in range(3)]
    assert out == ["sent", "sent", "skipped: daily limit"]


def test_provider_failure_is_recorded_and_never_raised(on, monkeypatch):
    monkeypatch.setattr(notify, "PROVIDER", "twilio")
    for k in ("TWILIO_SID", "TWILIO_TOKEN", "TWILIO_FROM"):
        monkeypatch.setattr(notify, k, "x")
    def boom(to, text):
        raise OSError("network down")
    monkeypatch.setattr(notify, "_send_twilio", boom)
    assert notify.send("down", "Tulasi", "high", MSG)["status"] == "failed"


def test_muted_block_sends_nothing(on):
    with notify.muted():
        assert notify.send("down", "Tulasi", "high", MSG) is None
    assert store.list("notifications") == []


def test_fast2sms_sends_the_ten_digit_number(on, monkeypatch):
    seen = {}

    class R:
        status = 200
        def read(self): return b'{"return": true}'
        def __enter__(self): return self
        def __exit__(self, *a): return False

    def fake(req, timeout=0):
        seen["body"], seen["key"] = req.data.decode(), req.get_header("Authorization")
        return R()

    monkeypatch.setattr(notify, "PROVIDER", "fast2sms")
    monkeypatch.setattr(notify, "FAST2SMS_KEY", "k123")
    monkeypatch.setattr(notify.urllib.request, "urlopen", fake)
    store.put(*notify.SETTINGS, {"phone": "+919876543210", "lang": "en", "enabled": True, "min_severity": "medium"})
    rec = notify.send("rest", "Tulasi", "medium", {"en": {"title": "x", "advice": "y"}})
    assert rec["status"] == "sent"
    assert "numbers=9876543210" in seen["body"] and "route=q" in seen["body"] and seen["key"] == "k123"


def test_fast2sms_refuses_non_indian_numbers(monkeypatch):
    monkeypatch.setattr(notify, "FAST2SMS_KEY", "k")
    with pytest.raises(ValueError):
        notify._send_fast2sms("+14155550100", "hi")
