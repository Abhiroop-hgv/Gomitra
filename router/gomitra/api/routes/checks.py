"""The checks the farmer app runs: a picture, a sound clip, and a walking/resting check."""
from fastapi import APIRouter

from gomitra.api.schemas import Analyze, AudioIn, Posture
from gomitra.services import analysis, audio, posture

router = APIRouter(prefix="/api", tags=["checks"])


@router.post("/analyze")
def analyze(a: Analyze):
    return analysis.analyze(a.image, a.mode, a.camera, a.cow_id, a.read_tags)


@router.post("/audio")
def audio_check(a: AudioIn):
    return audio.process_audio(a.audio, a.camera, a.immediate)


@router.post("/posture")
def posture_check(p: Posture):
    return posture.check_posture(p.images, p.cow_id, p.camera)
