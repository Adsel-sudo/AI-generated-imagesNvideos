from __future__ import annotations

import sys
from pathlib import Path

from sqlmodel import Session

from backend.app.db import engine
from backend.app.user_seed import seed_users_from_file

DATA_FILE = Path(__file__).with_name("seed_users.json")


def seed_users(update_password: bool = True) -> None:
    with Session(engine) as session:
        seed_users_from_file(session=session, data_file=DATA_FILE, update_password=update_password)


def main() -> None:
    update_password = True
    if len(sys.argv) > 1 and sys.argv[1] == "--skip-existing":
        update_password = False

    seed_users(update_password=update_password)


if __name__ == "__main__":
    main()
