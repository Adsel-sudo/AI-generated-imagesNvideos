import base64
import hashlib
import hmac
import os
from typing import Optional

from fastapi import Depends, HTTPException, Request, status
from sqlmodel import Session

from .db import engine
from .models import User

SESSION_USER_ID_KEY = "user_id"
PBKDF2_ITERATIONS = 200_000


def hash_password(password: str) -> str:
    password_text = (password or "").strip()
    if not password_text:
        raise ValueError("password cannot be empty")

    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password_text.encode("utf-8"), salt, PBKDF2_ITERATIONS)
    return "pbkdf2_sha256${iterations}${salt}${digest}".format(
        iterations=PBKDF2_ITERATIONS,
        salt=base64.b64encode(salt).decode("utf-8"),
        digest=base64.b64encode(digest).decode("utf-8"),
    )


def verify_password(password: str, password_hash: str) -> bool:
    if not password or not password_hash:
        return False

    try:
        algorithm, iterations_text, salt_b64, digest_b64 = password_hash.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        iterations = int(iterations_text)
        salt = base64.b64decode(salt_b64)
        expected_digest = base64.b64decode(digest_b64)
    except (ValueError, TypeError):
        return False

    actual_digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return hmac.compare_digest(actual_digest, expected_digest)


def set_session_user(request: Request, user: User) -> None:
    request.session[SESSION_USER_ID_KEY] = user.id


def clear_session_user(request: Request) -> None:
    request.session.pop(SESSION_USER_ID_KEY, None)


def get_current_user(request: Request) -> Optional[User]:
    user_id = request.session.get(SESSION_USER_ID_KEY)
    if not user_id:
        return None

    with Session(engine) as session:
        user = session.get(User, user_id)

    if not user:
        clear_session_user(request)
        return None

    return user


def require_login(user: Optional[User] = Depends(get_current_user)) -> User:
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="authentication required")
    return user
