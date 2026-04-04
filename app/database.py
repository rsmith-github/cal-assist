import os
from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, declarative_base, sessionmaker

from app.config import settings

# Ensure SQLite parent directory exists
_db_path = settings.database_url.replace("sqlite:///", "", 1)
if _db_path.startswith("./"):
    _db_path = os.path.join(os.getcwd(), _db_path[2:])
elif not os.path.isabs(_db_path):
    _db_path = os.path.join(os.getcwd(), _db_path)
_parent = os.path.dirname(os.path.abspath(_db_path))
if _parent:
    os.makedirs(_parent, exist_ok=True)

engine = create_engine(
    settings.database_url,
    connect_args={"check_same_thread": False},
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def init_db() -> None:
    from app import models  # noqa: F401 — register models

    Base.metadata.create_all(bind=engine)


def get_session() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
