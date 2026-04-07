import argparse

from sqlmodel import Session, select

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

    with Session(engine) as session:
        existing = session.exec(select(User).where(User.username == username)).first()
        if existing:
            raise SystemExit(f"user already exists: {username}")

        user = User(username=username, password_hash=hash_password(args.password))
        session.add(user)
        session.commit()
        session.refresh(user)

    print(f"created user: id={user.id} username={user.username}")


if __name__ == "__main__":
    main()
