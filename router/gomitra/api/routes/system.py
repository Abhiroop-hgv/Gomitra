"""Alerts, chewing and sounds, status, warm-up, demo data, health."""
from fastapi import APIRouter, Depends

from gomitra.api.deps import require_admin
from gomitra.services import alerts, demo, system

router = APIRouter(tags=["system"])


@router.get("/api/alerts")
def list_alerts():
    return alerts.list_open()


@router.post("/api/alerts/{aid}/resolve")
def resolve_alert(aid: str):
    alerts.resolve(aid)
    return {"ok": True}


@router.get("/api/feeding")
def feeding(camera: str = "Camera 1"):
    return system.feeding(camera)


@router.get("/api/sounds")
def sounds(camera: str = "North field camera"):
    return system.sounds(camera)


@router.post("/api/warmup")
def warmup():
    return system.warmup()


@router.get("/api/status")
def status():
    return system.status()


@router.get("/health")
def health():
    return {"status": "ok"}


@router.post("/api/demo/seed", dependencies=[Depends(require_admin)])
def seed():
    return {"added": demo.seed()}


@router.post("/api/demo/history", dependencies=[Depends(require_admin)])
def history():
    return demo.build_history()


@router.post("/api/demo/reset", dependencies=[Depends(require_admin)])
def reset(keep_cows: bool = False):
    return demo.reset(keep_cows)
