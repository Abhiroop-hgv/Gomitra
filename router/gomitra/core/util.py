"""Small helpers shared by the services."""
import base64
import time

from gomitra import config
from gomitra.errors import BadRequest, TooLarge


def now():
    return time.time()


def read_image(s: str) -> bytes:
    """Base64 (or a data URL) -> bytes. Used for photos, sound clips and videos alike."""
    if not s:
        raise BadRequest("image missing")
    raw = base64.b64decode(s.split(",", 1)[1] if s.startswith("data:") else s)
    if len(raw) > config.MAX_BYTES:
        raise TooLarge("image too large")
    return raw


def data_url(jpeg: bytes) -> str:
    return "data:image/jpeg;base64," + base64.b64encode(jpeg).decode()
