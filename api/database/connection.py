"""
Database connection configuration for the ValueInvestorsClub API.
"""
import os
from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

# Get DATABASE_URL from environment variable or use default
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    f"sqlite:///{Path(__file__).resolve().parents[2] / 'data' / 'vic_ideas.sqlite'}",
)
engine_args = {"connect_args": {"check_same_thread": False}} if DATABASE_URL.startswith("sqlite") else {
    "pool_size": 5,
    "max_overflow": 10,
}
engine = create_engine(DATABASE_URL, **engine_args)


# Dependency for database session
def get_db():
    """
    Creates and yields a database session.
    Uses a context manager to ensure the session is closed after use.
    """
    db = Session(engine)
    try:
        yield db
    finally:
        db.close()
