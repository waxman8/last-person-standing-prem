import os
from sqlmodel import Session, create_engine, select
from models import Competition
from services import retroactive_status_sync
import logging

# Setup logging to see our new DEBUG logs
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Use the bug DB
DATABASE_URL = "sqlite:///./lms-portugal-bug.db"
engine = create_engine(DATABASE_URL)

def reproduce():
    with Session(engine) as session:
        print("Running retroactive_status_sync on lms-portugal-bug.db...")
        count = retroactive_status_sync(session)
        print(f"Sync complete. Updated {count} statuses.")

if __name__ == "__main__":
    reproduce()
