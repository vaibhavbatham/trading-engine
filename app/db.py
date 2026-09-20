import logging
from contextlib import contextmanager
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.config import settings
from app.models import Base

logger = logging.getLogger(__name__)


def get_engine(database_url: str = None):
    url = database_url or settings.DATABASE_URL
    connect_args = {}
    if url.startswith("sqlite"):
        connect_args["check_same_thread"] = False
    return create_engine(url, connect_args=connect_args, pool_pre_ping=True)


engine = get_engine()
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_db(target_engine=None):
    """
    Creates all database tables if they do not exist.
    Alembic-free initialization for startup and test suites.
    """
    eng = target_engine or engine
    Base.metadata.create_all(bind=eng)

    # Auto-migrate SQLite schema if ticks table exists with legacy columns
    try:
        with eng.connect() as conn:
            cols = [row[1] for row in conn.exec_driver_sql("PRAGMA table_info(ticks)").fetchall()]
            if cols and "source" not in cols:
                conn.exec_driver_sql("ALTER TABLE ticks ADD COLUMN source VARCHAR(32) DEFAULT 'simulation'")
                logger.info("Migrated ticks table: added 'source' column.")
            if cols and "volume" not in cols:
                conn.exec_driver_sql("ALTER TABLE ticks ADD COLUMN volume NUMERIC(18, 4)")
                logger.info("Migrated ticks table: added 'volume' column.")
            conn.commit()
    except Exception as e:
        logger.debug("Schema migration check: %s", e)

    logger.info("Database tables initialized successfully.")


def get_db():
    """FastAPI dependency for database sessions."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def db_session(session_factory=None):
    """Context manager for non-FastAPI worker threads."""
    factory = session_factory or SessionLocal
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
