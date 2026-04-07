import argparse

from sqlmodel import Session, select

from app.auth import hash_password
from app.db import engine, init_db
from app.models import User


def main() -> None:
    parser = argparse.ArgumentParser(description="Reset password for an existing user")
    parser.add_argument("username", help="login username")
    parser.add_argument("password", help="new plain text password")
    args = parser.parse_args()

    username = args.username.strip()
    if not username:
        raise SystemExit("username cannot be empty")

    init_db()

    with Session(engine) as session:
        user = session.exec(select(User).where(User.username == username)).first()
        if not user:
            raise SystemExit(f"user not found: {username}")

        user.password_hash = hash_password(args.password)
        session.add(user)
        session.commit()

    print(f"password reset: username={username}")


if __name__ == "__main__":
    main()
