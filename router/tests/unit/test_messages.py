"""services/messages.py: farmer-facing text in English, Hindi and Telugu, and the fixed templates used when Gemini is unavailable."""
import pytest

from gomitra.services import messages

KINDS = ["lumpy", "fmd", "distress", "limp", "rest", "down", "eating"]


@pytest.mark.parametrize("kind", KINDS)
def test_every_alert_kind_has_a_complete_template_in_all_three_languages(kind):
    for lang in messages.LANGS:
        title, text, advice = messages.TEMPLATES[kind][lang]
        assert title.strip() and text.strip() and advice.strip()


@pytest.mark.parametrize("kind", KINDS)
def test_every_alert_kind_has_a_short_label_and_a_fact_for_gemini(kind):
    assert set(messages.SHORT[kind]) == {"en", "hi", "te"}
    assert messages.FACTS[kind].strip()


def test_the_template_names_the_cow():
    out = messages.template("lumpy", "Gauri")
    assert set(out) == {"en", "hi", "te"} and "Gauri" in out["en"]["text"] and "Gauri" in out["hi"]["text"]


def test_hindi_and_telugu_are_in_their_own_scripts():
    out = messages.template("down", "Tulasi")
    assert any("ऀ" <= ch <= "ॿ" for ch in out["hi"]["advice"])        # Devanagari
    assert any("ఀ" <= ch <= "౿" for ch in out["te"]["advice"])        # Telugu


def test_compose_without_gemini_gives_the_template_and_says_so():
    msg, source = messages.compose("fmd", "Nandini", use_gemini=False)
    assert source == "template" and msg == messages.template("fmd", "Nandini")


def test_compose_falls_back_to_the_template_when_gemini_fails():
    msg, source = messages.compose("limp", "Rani", passages=[{"source": "x", "text": "y"}])       # no Gemini in tests
    assert source == "template" and "Rani" in msg["en"]["text"]


def test_healthy_never_calls_gemini():
    assert messages.compose("healthy", "Rani")[1] == "template"
