from database import SessionLocal
from services import sync_fixtures_logic
import logging

# Setup logging to see what's happening
logging.basicConfig(level=logging.INFO)

def manual_sync():
    session = SessionLocal()
    try:
        print("Starting manual fixture sync for all active competitions...")
        result = sync_fixtures_logic(session)
        print(f"Sync Result: {result}")
    except Exception as e:
        print(f"Sync Failed: {e}")
    finally:
        session.close()

if __name__ == "__main__":
    manual_sync()
