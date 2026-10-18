"""Ask GoMitra and the vet-document library."""
from fastapi import APIRouter, Depends

from gomitra.api.deps import require_admin
from gomitra.api.schemas import Ask, KbDoc
from gomitra.services import assistant

router = APIRouter(prefix="/api", tags=["assistant"])


@router.post("/ask")
def ask(q: Ask):
    return assistant.ask(q.question, q.lang, q.cow_id)


@router.get("/kb")
def sources():
    return assistant.sources()


@router.post("/admin/kb", dependencies=[Depends(require_admin)])
def add_document(d: KbDoc):
    return {"source": d.source, "chunks": assistant.add_document(d.source, d.text, d.pdf)}


@router.delete("/admin/kb/{source}", dependencies=[Depends(require_admin)])
def remove_document(source: str):
    return {"removed": assistant.remove_document(source)}
