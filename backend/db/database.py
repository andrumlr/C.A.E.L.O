import os
from pathlib import Path

from sqlalchemy import create_engine, inspect, text
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


def get_data_dir() -> Path:
    """The same persistent directory the SQLite DB lives in — reuse this rather
    than recomputing CAELO_DATA_DIR elsewhere."""
    return _data_dir


# Columns added to existing tables after their initial release. create_all() only
# creates missing tables, it never alters existing ones, so new nullable columns
# need an explicit, additive ALTER TABLE here. Never remove entries — existing
# deployments rely on this running every startup until they've picked up the column.
_ADDED_COLUMNS: dict[str, list[str]] = {
    "documents": [
        "file_path VARCHAR",
        "content_type VARCHAR",
        "size_bytes INTEGER",
    ],
}


def _migrate_added_columns() -> None:
    inspector = inspect(engine)
    for table, column_defs in _ADDED_COLUMNS.items():
        if table not in inspector.get_table_names():
            continue  # brand-new DB — create_all() already made it with all columns
        existing = {col["name"] for col in inspector.get_columns(table)}
        with engine.begin() as conn:
            for column_def in column_defs:
                column_name = column_def.split()[0]
                if column_name in existing:
                    continue
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column_def}"))


def init_db():
    Base.metadata.create_all(bind=engine)
    _migrate_added_columns()
