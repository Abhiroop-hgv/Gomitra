"""Test setup: in-memory store, in-process models (when their weights exist), fake embeddings, no cloud calls.

The environment must be set before the `gomitra` package is imported, so it is done here at module level.
Gemini is not reachable in tests: every use of it falls back to the fixed templates, which is itself behaviour under test.
"""
import base64
import os
import sys
from pathlib import Path

ROUTER = Path(__file__).resolve().parents[1]
SERVING = ROUTER.parent / "serving"
os.environ.update(STORE="memory", INFER_BACKEND="local", EMBED_BACKEND="fake", ADMIN_KEY="test-admin", DEVICE_KEY="test-device",
                  AUTO_DEMO="1", SERVING_DIR=str(SERVING))
sys.path.insert(0, str(ROUTER))

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

SAMPLES = ROUTER / "static" / "samples"
HAVE_MODELS = (SERVING / "models" / "lsd_v2_3class.onnx").exists() and (SERVING / "models" / "yolo11n.onnx").exists()


def pytest_collection_modifyitems(config, items):
    if HAVE_MODELS:
        return
    skip = pytest.mark.skip(reason="model weights not found in serving/models (git lfs pull)")
    for item in items:
        if "models" in item.keywords:
            item.add_marker(skip)


@pytest.fixture(autouse=True)
def clean_state():
    """Every test starts with an empty store and empty caches."""
    from gomitra.context import store
    from gomitra.services import alerts, demo, ingest
    store.d.clear()
    alerts.clear_cache()
    ingest.clear_state()
    demo._hist_check["at"] = 0.0
    yield


@pytest.fixture
def client():
    """A fresh app (and so a fresh rate limiter) per test."""
    from gomitra.api.app import create_app
    return TestClient(create_app())


@pytest.fixture
def admin():
    return {"x-admin-key": "test-admin"}


@pytest.fixture
def device():
    return {"x-device-key": "test-device"}


@pytest.fixture
def seeded(client, admin):
    """The 6 demo cows plus the simulated week of habit data (Tulasi down for hours, group chewing low)."""
    client.post("/api/demo/seed", headers=admin)
    return client.post("/api/demo/history", headers=admin).json()


def sample_b64(name):
    return base64.b64encode((SAMPLES / name).read_bytes()).decode()


@pytest.fixture
def sample():
    return sample_b64
