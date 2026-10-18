"""Farmer sign-in: real accounts, hashed passwords, signed tokens, and the API locked only when AUTH_REQUIRED is on."""
import pytest

from gomitra import config
from gomitra.services import auth


@pytest.fixture
def farmer(client, admin):
    r = client.post("/api/users", headers=admin, json={"username": "Ramesh", "password": "cow-2026", "name": "Ramesh"})
    assert r.status_code == 200 and r.json()["username"] == "ramesh"
    return r.json()


def test_creating_an_account_needs_the_admin_key(client):
    assert client.post("/api/users", json={"username": "x1x", "password": "secret1"}).status_code == 403


def test_login_with_right_and_wrong_details(client, farmer):
    ok = client.post("/api/auth/login", json={"username": " RAMESH ", "password": "cow-2026"})
    assert ok.status_code == 200 and ok.json()["name"] == "Ramesh" and ok.json()["token"]
    bad = client.post("/api/auth/login", json={"username": "ramesh", "password": "nope"})
    unknown = client.post("/api/auth/login", json={"username": "ghost", "password": "cow-2026"})
    assert bad.status_code == unknown.status_code == 401 and bad.json() == unknown.json()


def test_password_is_not_stored_in_plain_text(client, farmer):
    from gomitra.context import store
    u = store.get("users", "ramesh")
    assert "cow-2026" not in str(u) and len(u["hash"]) == 64


def test_me_needs_a_valid_token(client, farmer):
    tok = client.post("/api/auth/login", json={"username": "ramesh", "password": "cow-2026"}).json()["token"]
    assert client.get("/api/auth/me", headers={"authorization": "Bearer " + tok}).json() == {"username": "ramesh", "name": "Ramesh"}
    assert client.get("/api/auth/me").status_code == 401
    assert client.get("/api/auth/me", headers={"authorization": "Bearer " + tok[:-2] + "xx"}).status_code == 401


def test_an_expired_token_is_refused(client, farmer, monkeypatch):
    tok = client.post("/api/auth/login", json={"username": "ramesh", "password": "cow-2026"}).json()["token"]
    monkeypatch.setattr(auth, "now", lambda: 9_999_999_999)
    assert client.get("/api/auth/me", headers={"authorization": "Bearer " + tok}).status_code == 401


def test_api_is_open_by_default_and_locked_when_required(client, farmer, monkeypatch):
    assert client.get("/api/cows").status_code == 200
    monkeypatch.setattr(config, "AUTH_REQUIRED", True)
    assert client.get("/api/cows").status_code == 401
    tok = client.post("/api/auth/login", json={"username": "ramesh", "password": "cow-2026"}).json()["token"]
    assert client.get("/api/cows", headers={"authorization": "Bearer " + tok}).status_code == 200


def test_admin_key_and_device_route_still_work_when_required(client, admin, monkeypatch):
    monkeypatch.setattr(config, "AUTH_REQUIRED", True)
    assert client.post("/api/demo/seed", headers=admin).status_code == 200
    assert auth.is_open("/api/ingest/frame", {"x-device-key": "k"}) and not auth.is_open("/api/ingest/frame", {})
