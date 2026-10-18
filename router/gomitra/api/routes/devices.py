"""The Raspberry Pi: one upload address, and a view of what the devices sent."""
from fastapi import APIRouter, Depends

from gomitra.api.deps import require_device
from gomitra.api.schemas import Ingest
from gomitra.services import ingest

router = APIRouter(prefix="/api/ingest", tags=["devices"])


@router.post("", dependencies=[Depends(require_device)])
def upload(b: Ingest):
    return ingest.handle(b.file, b.camera)


@router.get("/recent")
def recent():
    return ingest.recent()
