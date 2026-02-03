
from sqlmodel import Session, create_engine, SQLModel, select, and_
from models import User, Gameweek, Pick
from datetime import datetime, timedelta

# Setup in-memory DB
engine = create_engine("sqlite:///:memory:")
SQLModel.metadata.create_all(engine)

FIRST_GW_ID = 24

def check_pick_allowed(user, team_name, session):
    if user.number_of_re_entries > 0:
        prev_pick = session.exec(select(Pick).where(and_(
            Pick.user_id == user.id, 
            Pick.team_name == team_name,
            Pick.gameweek_id != FIRST_GW_ID
        ))).first()
    else:
        prev_pick = session.exec(select(Pick).where(and_(
            Pick.user_id == user.id, 
            Pick.team_name == team_name
        ))).first()
    
    return prev_pick is None

with Session(engine) as session:
    # 1. Create a user
    user = User(name="Test Player", pin="12345", is_active=True, number_of_re_entries=0)
    session.add(user)
    session.commit()
    session.refresh(user)

    # 2. Pick Team A in Week 24
    pick1 = Pick(user_id=user.id, gameweek_id=24, team_name="Arsenal")
    session.add(pick1)
    session.commit()

    # 3. Try picking Arsenal again (no re-entry) - Should be BLOCKED
    print(f"Test 1 (No re-entry, reuse Arsenal): {'ALLOWED' if check_pick_allowed(user, 'Arsenal', session) else 'BLOCKED'}")
    
    # 4. Try picking Chelsea (no re-entry) - Should be ALLOWED
    print(f"Test 2 (No re-entry, pick Chelsea): {'ALLOWED' if check_pick_allowed(user, 'Chelsea', session) else 'BLOCKED'}")

    # 5. Simulate re-entry
    user.number_of_re_entries = 1
    session.add(user)
    session.commit()

    # 6. Try picking Arsenal again (with re-entry) - Should be ALLOWED
    print(f"Test 3 (Re-entry 1, reuse Arsenal): {'ALLOWED' if check_pick_allowed(user, 'Arsenal', session) else 'BLOCKED'}")

    # 7. Pick Arsenal in Week 25
    pick2 = Pick(user_id=user.id, gameweek_id=25, team_name="Arsenal")
    session.add(pick2)
    session.commit()

    # 8. Try picking Arsenal again (with re-entry) - Should be BLOCKED (already reused once)
    print(f"Test 4 (Re-entry 1, reuse Arsenal again): {'ALLOWED' if check_pick_allowed(user, 'Arsenal', session) else 'BLOCKED'}")

    # 9. Pick Chelsea in Week 26
    pick3 = Pick(user_id=user.id, gameweek_id=26, team_name="Chelsea")
    session.add(pick3)
    session.commit()

    # 10. Try picking Chelsea again - Should be BLOCKED (Chelsea was not Week 24)
    print(f"Test 5 (Re-entry 1, reuse Chelsea): {'ALLOWED' if check_pick_allowed(user, 'Chelsea', session) else 'BLOCKED'}")
