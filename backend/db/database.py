from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from .models import Base

_backend_dir = Path(__file__).resolve().parent.parent
_db_file = _backend_dir / "caelo.db"
# Absolute path so the DB stays in backend/ no matter which cwd uvicorn uses.
_engine_url = f"sqlite:///{_db_file.resolve().as_posix()}"
engine = create_engine(_engine_url)
SessionLocal = sessionmaker(bind=engine)

def init_db():
    Base.metadata.create_all(bind=engine)
