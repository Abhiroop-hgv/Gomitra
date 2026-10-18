"""core/tracing.py: the measured list of steps shown as "Behind this result"."""
import contextvars
import time

from gomitra.core import tracing as trace


def fresh(fn):
    """Run fn in a copy of the context so one test's trace cannot leak into another."""
    return contextvars.copy_context().run(fn)


def test_no_trace_started_means_nothing_is_recorded():
    def run():
        with trace.step("Gemini", "x"):
            pass
        return trace.get()
    assert fresh(run) == []


def test_steps_are_recorded_with_a_measured_time():
    def run():
        trace.start()
        with trace.step("Vertex AI endpoint", "predict"):
            time.sleep(0.02)
        return trace.get()
    (s,) = fresh(run)
    assert s["service"] == "Vertex AI endpoint" and s["detail"] == "predict" and s["ms"] >= 15


def test_repeated_calls_of_one_kind_can_be_merged_into_one_line():
    def run():
        trace.start()
        for _ in range(3):
            with trace.step("Firestore", "{n} reads/writes", aggregate=True):
                pass
        return trace.get()
    (s,) = fresh(run)
    assert s["service"] == "Firestore" and s["detail"] == "3 reads/writes"


def test_a_failed_step_says_so_and_the_error_still_propagates():
    def run():
        trace.start()
        try:
            with trace.step("Gemini", "answer"):
                raise ValueError("boom")
        except ValueError:
            return trace.get()
    (s,) = fresh(run)
    assert "failed: ValueError" in s["detail"]


def test_a_nested_start_keeps_the_callers_trace():
    def run():
        trace.start()
        with trace.step("A", "outer"):
            pass
        trace.start()                       # e.g. ingest calling analyze: must not wipe the steps so far
        with trace.step("B", "inner"):
            pass
        return [x["service"] for x in trace.get()]
    assert fresh(run) == ["A", "B"]
