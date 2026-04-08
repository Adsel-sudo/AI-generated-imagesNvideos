from __future__ import annotations

import json
import sys
from pathlib import Path

from sqlmodel import Session, select

from app.auth import hash_password
from app.db import engine
from app.models import User

DATA_FILE = Path(__file__).with_name("seed_users.json")


def load_seed_data(data_file: Path = DATA_FILE) -> list[dict[str, str]]:
    if not data_file.exists():
        raise FileNotFoundError(
            f"未找到种子数据文件: {data_file}\n"
            f"请创建该文件，并写入账号列表。"
        )

    with data_file.open("r", encoding="utf-8") as f:
        data = json.load(f)

    if not isinstance(data, list):
        raise ValueError("seed_users.json 必须是数组格式。")

    normalized: list[dict[str, str]] = []
    for i, item in enumerate(data, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"第 {i} 项不是对象。")

        username = str(item.get("username", "")).strip()
        password = str(item.get("password", "")).strip()

        if not username:
            raise ValueError(f"第 {i} 项缺少 username。")
        if not password:
            raise ValueError(f"第 {i} 项缺少 password。")

        normalized.append({"username": username, "password": password})

    return normalized


def seed_users_from_file(
    session: Session,
    data_file: Path = DATA_FILE,
    update_password: bool = True,
) -> None:
    users = load_seed_data(data_file)

    created = 0
    updated = 0
    skipped = 0

    for item in users:
        username = item["username"]
        password = item["password"]

        existing = session.exec(select(User).where(User.username == username)).first()

        password_hash = hash_password(password)

        if existing:
            if update_password:
                existing.password_hash = password_hash
                session.add(existing)
                updated += 1
                print(f"[UPDATED] {username}")
            else:
                skipped += 1
                print(f"[SKIPPED] {username}")
        else:
            user = User(username=username, password_hash=password_hash)
            session.add(user)
            created += 1
            print(f"[CREATED] {username}")

    session.commit()

    print(
        f"\n完成: created={created}, updated={updated}, skipped={skipped}, total={len(users)}"
    )


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
