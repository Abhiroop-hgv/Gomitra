"""Settings and tunable constants in one place. Read from the environment once, at import time.

Model and Gemini settings (INFER_BACKEND, ENDPOINT_ID, GEMINI_MODEL, ...) live next to the code that uses them
(infra/inference.py, services/messages.py, services/kb.py); this file holds the settings the whole app shares.
"""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATIC_DIR = ROOT / "static"

ADMIN_KEY = os.getenv("ADMIN_KEY", "")           # protects admin routes (vet documents, demo data, deleting a cow)
DEVICE_KEY = os.getenv("DEVICE_KEY", "")         # shared secret of the Raspberry Pi uploader
AUTH_REQUIRED = os.getenv("AUTH_REQUIRED", "0") == "1"   # farmers must sign in (username + password) to use /api; off = open, as before
AUTH_SECRET = os.getenv("AUTH_SECRET", "")       # signs the login tokens; set it (a long random string) when AUTH_REQUIRED=1
FARMER_USER = os.getenv("FARMER_USER", "")         # optional: a farmer account created at start-up if it does not exist yet
FARMER_PASS = os.getenv("FARMER_PASS", "")
FARMER_NAME = os.getenv("FARMER_NAME", "")
AUTH_TOKEN_HOURS = 24 * 7                        # how long a login lasts
AUTO_DEMO = os.getenv("AUTO_DEMO", "1") == "1"   # rebuild the simulated week of habit data when the app opens

FACE_MATCH = 0.69        # cosine threshold from the cattle_id repo (1% false accepts on close-ups); retune on real data
MAX_BYTES = 8_000_000    # largest upload accepted (decoded)
POSTURE_EVERY = 600      # seconds between walking/resting checks for the same cow (the pose model is the slow one)

# Per-visitor allowance per minute and kind of call. The app is public and every call costs money (models, Gemini).
# (path match, calls per minute). "/report" matches by suffix, everything else by prefix.
RATE_LIMITS = [("/api/ingest", 90), ("/api/warmup", 6), ("/api/posture", 20), ("/api/analyze", 30),
               ("/api/audio", 30), ("/api/ask", 30), ("/api/auth/login", 10), ("/report", 15), ("/api/cows", 30)]
