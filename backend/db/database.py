import os
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from .models import Base

_data_dir_env = os.environ.get("CAELO_DATA_DIR")
if _data_dir_env:
    _data_dir = Path(_data_dir_env)
else:
    _data_dir = Path(__file__).resolve().parent.parent  # fallback: backend/
_data_dir.mkdir(parents=True, exist_ok=True)
_db_file = _data_dir / "caelo.db"
# Absolute path so the DB stays in backend/ no matter which cwd uvicorn uses.
_engine_url = f"sqlite:///{_db_file.resolve().as_posix()}"
engine = create_engine(_engine_url)
SessionLocal = sessionmaker(bind=engine)

def init_db():
    Base.metadata.create_all(bind=engine)
