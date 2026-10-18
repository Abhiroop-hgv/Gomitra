"""Farmer sign-in and (admin) account creation."""
from fastapi import APIRouter, Depends, Header

from gomitra.api.deps import require_admin
from gomitra.api.schemas import Credentials, NewUser
from gomitra.services import auth

router = APIRouter(tags=["auth"])


@router.post("/api/auth/login")
def login(body: Credentials):
    return auth.login(body.username, body.password)


@router.get("/api/auth/me")
def me(authorization: str = Header("")):
    return auth.user_from_header(authorization)


@router.post("/api/users", dependencies=[Depends(require_admin)])
def create_user(body: NewUser):
    return auth.create_user(body.username, body.password, body.name, body.phone)
