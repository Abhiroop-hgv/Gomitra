"""Cows: list, register, read, resolve, delete; habit trends and the vet report."""
from fastapi import APIRouter, Depends

from gomitra.api.deps import require_admin
from gomitra.api.schemas import Register
from gomitra.services import cows, system

router = APIRouter(prefix="/api/cows", tags=["cows"])


@router.post("")
def register(r: Register):
    return cows.register(r.name, r.tag, r.breed, r.age, r.photos)


@router.get("")
def list_cows():
    return cows.list_public()


@router.get("/{cid}")
def get_cow(cid: str):
    return cows.public(cows.get_cow(cid))


@router.get("/{cid}/trends")
def trends(cid: str):
    return system.cow_trends(cid)


@router.get("/{cid}/report")
def vet_report(cid: str, lang: str = "en"):
    return system.vet_report(cid, lang)


@router.post("/{cid}/resolve")
def resolve(cid: str):
    cows.resolve(cid)
    return {"ok": True}


@router.delete("/{cid}", dependencies=[Depends(require_admin)])
def remove(cid: str):
    cows.remove(cid)
    return {"ok": True}
