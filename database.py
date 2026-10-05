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
        
        # Check for UserCompetitionStatus.status
        cursor = conn.execute(text("PRAGMA table_info(usercompetitionstatus)"))
        columns = [row[1] for row in cursor.fetchall()]
        if "status" not in columns:
            # Add status column
            conn.execute(text("ALTER TABLE usercompetitionstatus ADD COLUMN status VARCHAR DEFAULT 'ACTIVE'"))
            # For existing records, if is_active was true, status is ACTIVE, else OUT
            if "is_active" in columns:
                conn.execute(text("UPDATE usercompetitionstatus SET status = 'ACTIVE' WHERE is_active = 1"))
                conn.execute(text("UPDATE usercompetitionstatus SET status = 'OUT' WHERE is_active = 0"))
            print("Migration: Added status to usercompetitionstatus table")

        # Check for UserCompetitionStatus.last_re_entry_gw_id
        cursor = conn.execute(text("PRAGMA table_info(usercompetitionstatus)"))
        columns = [row[1] for row in cursor.fetchall()]
        if "last_re_entry_gw_id" not in columns:
            conn.execute(text("ALTER TABLE usercompetitionstatus ADD COLUMN last_re_entry_gw_id INTEGER DEFAULT 0"))
            print("Migration: Added last_re_entry_gw_id to usercompetitionstatus table")

        # Check for UserCompetitionStatus.has_paid_reentry
        cursor = conn.execute(text("PRAGMA table_info(usercompetitionstatus)"))
        columns = [row[1] for row in cursor.fetchall()]
        if "has_paid_reentry" not in columns:
            conn.execute(text("ALTER TABLE usercompetitionstatus ADD COLUMN has_paid_reentry BOOLEAN DEFAULT 0"))
            print("Migration: Added has_paid_reentry to usercompetitionstatus table")

        # Migration: Ensure all datetimes are stored with UTC offset
        conn.execute(text("UPDATE gameweek SET deadline = deadline || '+00:00' WHERE deadline NOT LIKE '%+00:00' AND deadline NOT LIKE '%Z'"))
        conn.execute(text("UPDATE fixture SET kickoff_time = kickoff_time || '+00:00' WHERE kickoff_time NOT LIKE '%+00:00' AND kickoff_time NOT LIKE '%Z'"))
        conn.execute(text("UPDATE pick SET timestamp = timestamp || '+00:00' WHERE timestamp NOT LIKE '%+00:00' AND timestamp NOT LIKE '%Z'"))
        print("Migration: Appended UTC offset to existing naive datetimes")

        # Check for Competition.entry_fee
        cursor = conn.execute(text("PRAGMA table_info(competition)"))
        columns = [row[1] for row in cursor.fetchall()]
        if "entry_fee" not in columns:
            conn.execute(text("ALTER TABLE competition ADD COLUMN entry_fee FLOAT DEFAULT 5.0"))
            # Specifically update PL 26/27 to 7.5
            conn.execute(text("UPDATE competition SET entry_fee = 7.5 WHERE name LIKE '%Premier League 26/27%' OR code = 'PL'"))
            print("Migration: Added entry_fee to competition table and updated PL fee")

        conn.commit()

def init_db():
    SQLModel.metadata.create_all(engine)
    run_migrations()

def get_session():
    with Session(engine) as session:
        yield session
