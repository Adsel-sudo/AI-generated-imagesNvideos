from __future__ import annotations

import argparse
import sys
from pathlib import Path

from sqlmodel import Session, select

backend_dir = str(Path(__file__).resolve().parents[1])
if backend_dir not in sys.path:
    sys.path.append(backend_dir)

from app.db import engine, init_db
from app.models import User


def main() -> None:
    parser = argparse.ArgumentParser(description="Delete an existing user")
    parser.add_argument("username", help="login username")
    args = parser.parse_args()

    username = args.username.strip()
    if not username:
        raise SystemExit("username cannot be empty")

    init_db()

    with Session(engine) as session:
        user = session.exec(select(User).where(User.username == username)).first()
        if not user:
            print(f"[NOT FOUND] {username}")
            raise SystemExit(1)

        session.delete(user)
        session.commit()

    print(f"[DELETED] {username}")


if __name__ == "__main__":
    main()
