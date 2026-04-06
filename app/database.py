import os
from contextlib import contextmanager
from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, declarative_base, sessionmaker

from app.config import settings

def _ensure_sqlite_parent_dir(db_url: str) -> None:
    if not db_url.startswith("sqlite:///"):
        return
    db_path = db_url.replace("sqlite:///", "", 1)
    if db_path.startswith("./"):
        db_path = os.path.join(os.getcwd(), db_path[2:])
    elif not os.path.isabs(db_path):
        db_path = os.path.join(os.getcwd(), db_path)
    parent = os.path.dirname(os.path.abspath(db_path))
    if parent:
        os.makedirs(parent, exist_ok=True)


def _build_sessionmaker(db_url: str) -> sessionmaker:
    _ensure_sqlite_parent_dir(db_url)
    engine = create_engine(db_url, connect_args={"check_same_thread": False})
    return sessionmaker(autocommit=False, autoflush=False, bind=engine)


SessionLocal = _build_sessionmaker(settings.database_url)
DevSessionLocal = _build_sessionmaker(settings.dev_database_url)
Base = declarative_base()


def init_db() -> None:
    from app import models  # noqa: F401 — register models

    Base.metadata.create_all(bind=SessionLocal.kw["bind"])
    if settings.dev_mode:
        Base.metadata.create_all(bind=DevSessionLocal.kw["bind"])


def _sessionmaker_for_user(user_id: int) -> sessionmaker:
    if settings.dev_mode and user_id == settings.dev_mode_user_id:
        return DevSessionLocal
    return SessionLocal


@contextmanager
def user_session(user_id: int) -> Generator[Session, None, None]:
    db = _sessionmaker_for_user(user_id)()
    try:
        yield db
    finally:
        db.close()


def get_session() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
