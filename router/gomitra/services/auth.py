"""Farmer sign-in: username + password, checked here; a signed token (HMAC, stdlib only) says who is signed in.

Accounts live in the `users` collection (password stored as a salted PBKDF2 hash, never in plain text). Accounts are made by us
(`create_user`, or the admin route), not by self sign-up. With AUTH_REQUIRED=1 the API needs the token; the Raspberry Pi route
keeps its own device key and the admin key still works, so the cameras and the admin tools are not affected.
"""
import base64
import hashlib
import hmac
import json
import secrets

from gomitra import config
from gomitra.context import store
from gomitra.core.util import now
from gomitra.errors import BadRequest, Unauthorized

_ITER = 200_000
_fallback_secret = secrets.token_bytes(32)          # used only when AUTH_SECRET is not set (tokens then die on restart)


def _secret():
    return config.AUTH_SECRET.encode() if config.AUTH_SECRET else _fallback_secret


def _hash(password, salt):
    return hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), _ITER).hex()


def _norm(username):
    return "".join(ch for ch in (username or "").strip().lower() if not ch.isspace())


def create_user(username, password, name="", phone=""):
    """Add or replace a farmer account. -> public profile."""
    u = _norm(username)
    if len(u) < 3 or len(password or "") < 6:
        raise BadRequest("username needs 3+ characters and password 6+ characters")
    salt = secrets.token_hex(16)
    store.put("users", u, {"username": u, "salt": salt, "hash": _hash(password, salt), "name": name or u, "phone": phone,
                           "created": now()})
    return {"username": u, "name": name or u}


def _sign(payload):
    body = base64.urlsafe_b64encode(json.dumps(payload, separators=(",", ":")).encode()).decode().rstrip("=")
    sig = hmac.new(_secret(), body.encode(), hashlib.sha256).hexdigest()
    return body + "." + sig


def _read(token):
    try:
        body, sig = token.split(".")
        if not hmac.compare_digest(sig, hmac.new(_secret(), body.encode(), hashlib.sha256).hexdigest()):
            raise ValueError
        payload = json.loads(base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)))
        if payload["exp"] < now():
            raise ValueError
        return payload
    except Exception:
        raise Unauthorized("Please sign in again.")


def login(username, password):
    """-> {"token", "username", "name"}. The same message for a wrong name and a wrong password."""
    u = store.get("users", _norm(username))
    ok = bool(u) and hmac.compare_digest(u["hash"], _hash(password or "", u["salt"]))
    if not ok:
        raise Unauthorized("Wrong username or password.")
    token = _sign({"u": u["username"], "exp": now() + config.AUTH_TOKEN_HOURS * 3600})
    return {"token": token, "username": u["username"], "name": u["name"]}


def user_from_header(authorization):
    """'Bearer <token>' -> the signed-in account's profile, or raises Unauthorized."""
    if not authorization.lower().startswith("bearer "):
        raise Unauthorized("Please sign in.")
    p = _read(authorization[7:].strip())
    u = store.get("users", p["u"])
    if not u:
        raise Unauthorized("Please sign in again.")
    return {"username": u["username"], "name": u["name"]}


def is_open(path, headers):
    """Paths that need no sign-in even when AUTH_REQUIRED: login itself, and the Pi route (it checks its own device key)."""
    return path == "/api/auth/login" or (path.startswith("/api/ingest") and bool(headers.get("x-device-key")))


def ensure_env_user():
    """Start-up: create the farmer account named in FARMER_USER / FARMER_PASS if it is not there yet (never overwrites)."""
    if config.FARMER_USER and config.FARMER_PASS and not store.get("users", _norm(config.FARMER_USER)):
        create_user(config.FARMER_USER, config.FARMER_PASS, config.FARMER_NAME)
