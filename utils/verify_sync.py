import os
from database import engine
from sqlmodel import Session, select
from services import sync_fixtures_logic
from models import Fixture

def verify():
    if not os.getenv("FOOTBALL_DATA_API_KEY"):
        print("Error: FOOTBALL_DATA_API_KEY not set")
        return

    # Run the sync logic
    with Session(engine) as session:
        print("Starting sync...")
        try:
            result = sync_fixtures_logic(session)
            print(f"Sync result: {result}")
            
            # Check the specific fixture
            fixture = session.exec(select(Fixture).where(Fixture.id == 537428)).first()
            if fixture:
                print(f"\nFixture 537428 (Australia vs Egypt):")
                print(f"Status: {fixture.status}")
                print(f"Winner: {fixture.winner}")
                print(f"Score: {fixture.home_score} - {fixture.away_score}")
                
                if fixture.winner == "Egypt":
                     print("\nSUCCESS: Winner derived correctly!")
                else:
                     print(f"\nFAILURE: Winner is {fixture.winner}")
            else:
                print("Fixture not found in DB.")
        except Exception as e:
            print(f"Error during verification: {e}")
            import traceback
            traceback.print_exc()

if __name__ == "__main__":
    verify()
