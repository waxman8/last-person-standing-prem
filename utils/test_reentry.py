
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from sqlmodel import Session, create_engine, SQLModel, select, and_
from models import User, Gameweek, Pick, Competition, UserCompetitionStatus
from datetime import datetime, timedelta

# Setup in-memory DB
engine = create_engine("sqlite:///:memory:")
SQLModel.metadata.create_all(engine)

FIRST_GW_ID = 24

def check_pick_allowed(user_status, team_name, session):
    if user_status.number_of_re_entries > 0:
        prev_pick = session.exec(select(Pick).where(and_(
            Pick.user_id == user_status.user_id, 
            Pick.team_name == team_name,
            Pick.gameweek_id != FIRST_GW_ID
        ))).first()
    else:
        prev_pick = session.exec(select(Pick).where(and_(
            Pick.user_id == user_status.user_id, 
            Pick.team_name == team_name
        ))).first()
    
    return prev_pick is None

with Session(engine) as session:
    # 0. Create Competition
    comp = Competition(name="Premier League", code="PL")
    session.add(comp)
    session.commit()
    session.refresh(comp)

    # 1. Create a user and status
    user = User(name="Test Player", pin="12345", is_active=True)
    session.add(user)
    session.commit()
    session.refresh(user)

    status = UserCompetitionStatus(user_id=user.id, competition_id=comp.id, is_active=True, number_of_re_entries=0)
    session.add(status)
    session.commit()
    session.refresh(status)

    # 2. Pick Team A in Week 24
    pick1 = Pick(user_id=user.id, gameweek_id=24, team_name="Arsenal", competition_id=comp.id)
    session.add(pick1)
    session.commit()

    # 3. Try picking Arsenal again (no re-entry) - Should be BLOCKED
    print(f"Test 1 (No re-entry, reuse Arsenal): {'ALLOWED' if check_pick_allowed(status, 'Arsenal', session) else 'BLOCKED'}")
    
    # 4. Try picking Chelsea (no re-entry) - Should be ALLOWED
    print(f"Test 2 (No re-entry, pick Chelsea): {'ALLOWED' if check_pick_allowed(status, 'Chelsea', session) else 'BLOCKED'}")

    # 5. Simulate re-entry
    status.number_of_re_entries = 1
    session.add(status)
    session.commit()

    # 6. Try picking Arsenal again (with re-entry) - Should be ALLOWED
    print(f"Test 3 (Re-entry 1, reuse Arsenal): {'ALLOWED' if check_pick_allowed(status, 'Arsenal', session) else 'BLOCKED'}")

    # 7. Pick Arsenal in Week 25
    pick2 = Pick(user_id=user.id, gameweek_id=25, team_name="Arsenal", competition_id=comp.id)
    session.add(pick2)
    session.commit()

    # 8. Try picking Arsenal again (with re-entry) - Should be BLOCKED (already reused once)
    print(f"Test 4 (Re-entry 1, reuse Arsenal again): {'ALLOWED' if check_pick_allowed(status, 'Arsenal', session) else 'BLOCKED'}")

    # 9. Pick Chelsea in Week 26
    pick3 = Pick(user_id=user.id, gameweek_id=26, team_name="Chelsea", competition_id=comp.id)
    session.add(pick3)
    session.commit()

    # 10. Try picking Chelsea again - Should be BLOCKED (Chelsea was not Week 24)
    print(f"Test 5 (Re-entry 1, reuse Chelsea): {'ALLOWED' if check_pick_allowed(status, 'Chelsea', session) else 'BLOCKED'}")
