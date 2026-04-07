from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel
from sqlmodel import Session, select

from .auth import clear_session_user, get_current_user, set_session_user, verify_password
from .db import engine
from .models import User

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginRequest(BaseModel):
    username: str
    password: str


@router.post("/login")
def login(payload: LoginRequest, request: Request):
    username = payload.username.strip()
    if not username or not payload.password:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="username and password are required")

    with Session(engine) as session:
        user = session.exec(select(User).where(User.username == username)).first()

    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid username or password")

    set_session_user(request, user)
    return {"user": {"id": user.id, "username": user.username}}


@router.post("/logout")
def logout(request: Request):
    clear_session_user(request)
    return {"ok": True}


@router.get("/me")
def me(request: Request):
    user = get_current_user(request)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="not logged in")
    return {"user": {"id": user.id, "username": user.username}}
