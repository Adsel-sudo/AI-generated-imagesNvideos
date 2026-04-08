from __future__ import annotations

import argparse
import sys
from pathlib import Path

from sqlmodel import Session, select

backend_dir = str(Path(__file__).resolve().parents[1])
if backend_dir not in sys.path:
    sys.path.append(backend_dir)

from app.auth import hash_password
from app.db import engine, init_db
from app.models import User


def main() -> None:
    parser = argparse.ArgumentParser(description="Create a new user for the workbench")
    parser.add_argument("username", help="login username")
    parser.add_argument("password", help="plain text password")
    args = parser.parse_args()

    username = args.username.strip()
    if not username:
        raise SystemExit("username cannot be empty")

    init_db()

    status = ""
    with Session(engine) as session:
        existing = session.exec(select(User).where(User.username == username)).first()
        if existing:
            status = "EXISTS"
        else:
            user = User(username=username, password_hash=hash_password(args.password))
            session.add(user)
            session.commit()
            status = "CREATED"

    print(f"[{status}] {username}")
    print(f"summary: username={username} status={status}")


if __name__ == "__main__":
    main()
