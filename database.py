from sqlmodel import create_engine, SQLModel, Session, text
import os

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./lms.db")

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})

# Explicit Session factory for background workers
def SessionLocal():
    return Session(engine)

def run_migrations():
    """Simple migration logic to add columns if they are missing."""
    with engine.connect() as conn:
        # Check for Gameweek.is_rollover
        cursor = conn.execute(text("PRAGMA table_info(gameweek)"))
        columns = [row[1] for row in cursor.fetchall()]
        if "is_rollover" not in columns:
            conn.execute(text("ALTER TABLE gameweek ADD COLUMN is_rollover BOOLEAN DEFAULT 0"))
            print("Migration: Added is_rollover to gameweek table")

        # Check for User.number_of_rollover_re_entries
        cursor = conn.execute(text("PRAGMA table_info(user)"))
        columns = [row[1] for row in cursor.fetchall()]
        if "number_of_rollover_re_entries" not in columns:
            conn.execute(text("ALTER TABLE user ADD COLUMN number_of_rollover_re_entries INTEGER DEFAULT 0"))
            print("Migration: Added number_of_rollover_re_entries to user table")
        
        conn.commit()

def init_db():
    SQLModel.metadata.create_all(engine)
    run_migrations()

def get_session():
    with Session(engine) as session:
        yield session
