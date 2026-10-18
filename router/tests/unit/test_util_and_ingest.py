"""core/util.py and the pure parts of services/ingest.py."""
import base64

import cv2
import numpy as np
import pytest

from gomitra.core import util
from gomitra.errors import AppError, BadRequest, Forbidden, NotFound, TooLarge, Unprocessable, UnsupportedMedia, UpstreamError
from gomitra.services import ingest


def test_read_image_accepts_plain_base64_and_data_urls():
    raw = b"\xff\xd8\xff hello"
    b64 = base64.b64encode(raw).decode()
    assert util.read_image(b64) == raw and util.read_image("data:image/jpeg;base64," + b64) == raw


def test_read_image_rejects_empty_and_oversize(monkeypatch):
    with pytest.raises(BadRequest):
        util.read_image("")
    monkeypatch.setattr(util.config, "MAX_BYTES", 10)
    with pytest.raises(TooLarge):
        util.read_image(base64.b64encode(b"x" * 11).decode())


def test_data_url_round_trips():
    assert util.data_url(b"abc") == "data:image/jpeg;base64," + base64.b64encode(b"abc").decode()


def test_errors_carry_http_statuses():
    assert [e.status for e in (BadRequest, Forbidden, NotFound, TooLarge, UnsupportedMedia, Unprocessable, UpstreamError)] == \
           [400, 403, 404, 413, 415, 422, 502]
    assert isinstance(NotFound("x"), AppError) and NotFound("gone").detail == "gone"


@pytest.mark.parametrize("head,kind", [
    (b"\xff\xd8\xff\xe0 jpeg", "image"),
    (b"\x89PNG\r\n\x1a\n rest", "image"),
    (b"RIFF\x00\x00\x00\x00WAVEfmt ", "audio"),
    (b"\x00\x00\x00\x18ftypmp42", "video"),
    (b"\x1aE\xdf\xa3 webm", "video"),
    (b"hello world", None),
    (b"", None),
])
def test_sniff_recognises_files_by_their_first_bytes(head, kind):
    assert ingest.sniff(head) == kind


def test_video_frames_are_sampled_in_time_order(tmp_path):
    path = tmp_path / "t.mp4"
    vw = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), 6, (320, 240))
    rng = np.random.default_rng(0)
    for _ in range(30):                                            # 5 seconds at 6 frames a second
        vw.write(rng.integers(0, 255, (240, 320, 3), dtype=np.uint8))
    vw.release()
    frames = ingest.video_frames(path.read_bytes(), per_s=2.0, max_n=24)
    times = [t for t, _ in frames]
    assert 8 <= len(frames) <= 11 and times == sorted(times) and times[0] == 0.0
    assert all(jpeg[:3] == b"\xff\xd8\xff" for _, jpeg in frames)
    assert len(ingest.video_frames(path.read_bytes(), per_s=6.0, max_n=5)) == 5          # capped, spread over the clip
