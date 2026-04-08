from __future__ import annotations

import sys
from pathlib import Path

from sqlmodel import Session, select

backend_dir = str(Path(__file__).resolve().parents[1])
if backend_dir not in sys.path:
    sys.path.append(backend_dir)

from app.db import engine, init_db
from app.models import User


def main() -> None:
    init_db()

    with Session(engine) as session:
        users = session.exec(select(User).order_by(User.username)).all()

    print(f"total={len(users)}")
    for user in users:
        print(user.username)


if __name__ == "__main__":
    main()
