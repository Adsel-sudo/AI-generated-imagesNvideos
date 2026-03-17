from contextlib import contextmanager

from sqlalchemy import text
from sqlmodel import Session, SQLModel, create_engine

from .config import settings

connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
engine = create_engine(settings.database_url, connect_args=connect_args)


def _ensure_output_target_type_column() -> None:
    if not settings.database_url.startswith("sqlite"):
        return

    with engine.begin() as conn:
        table_exists = conn.execute(
            text("SELECT name FROM sqlite_master WHERE type='table' AND name='output'")
        ).first()
        if not table_exists:
            return

        columns = conn.execute(text("PRAGMA table_info('output')")).fetchall()
        column_names = {str(column[1]) for column in columns}
        if "target_type" not in column_names:
            conn.execute(text("ALTER TABLE output ADD COLUMN target_type TEXT"))


def init_db() -> None:
    SQLModel.metadata.create_all(engine)
    _ensure_output_target_type_column()


@contextmanager
def get_session():
    with Session(engine) as session:
        yield session
