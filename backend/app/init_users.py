from pathlib import Path

from sqlalchemy import func
from sqlmodel import Session, select

from app.db import engine
from app.models import User
from scripts.seed_users import seed_users_from_file

SEED_USERS_FILE = Path(__file__).resolve().parent.parent / "scripts" / "seed_users.json"


def init_users_if_empty() -> None:
    try:
        with Session(engine) as session:
            user_count = session.exec(select(func.count()).select_from(User)).one()

            if user_count == 0:
                if not SEED_USERS_FILE.exists():
                    print(f"[INIT][WARN] seed users file not found, skip seeding: {SEED_USERS_FILE}")
                    return

                print("[INIT] user table empty, seeding users...")
                seed_users_from_file(session=session, data_file=SEED_USERS_FILE)
                return

            print("[INIT] user table already initialized, skip seeding")
    except Exception as exc:
        print(f"[INIT][WARN] failed to initialize users: {exc}")
