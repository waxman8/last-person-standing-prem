from sqlmodel import Session, create_engine, select
from models import Competition, UserCompetitionStatus, User
import os

DATABASE_URL = "sqlite:///lms.db"
engine = create_engine(DATABASE_URL)

def test_prize_pot():
    with Session(engine) as session:
        competition_id = 3
        comp = session.get(Competition, competition_id)
        if not comp:
            print("Competition not found")
            return
        
        entry_fee = comp.entry_fee
        print(f"Competition: {comp.name}, Entry Fee: {entry_fee}")
        
        statuses = session.exec(select(UserCompetitionStatus).where(UserCompetitionStatus.competition_id == competition_id)).all()
        
        total_re_entries = sum(s.number_of_re_entries for s in statuses)
        total_queued_re_entries = sum(1 for s in statuses if getattr(s, 'has_paid_reentry', False))
        total_rollover_re_entries = sum(getattr(s, 'number_of_rollovers', 0) for s in statuses)
        paid_entries = sum(1 for s in statuses if s.paid or s.status in ['ACTIVE', 'OUT'])
        
        prize_pot = (paid_entries + total_re_entries + total_queued_re_entries + total_rollover_re_entries) * entry_fee
        print(f"Paid Entries: {paid_entries}")
        print(f"Re-entries: {total_re_entries}")
        print(f"Queued: {total_queued_re_entries}")
        print(f"Rollover: {total_rollover_re_entries}")
        print(f"Prize Pot: {prize_pot}")
        
        expected_pot = (paid_entries + total_re_entries + total_queued_re_entries + total_rollover_re_entries) * 7.5
        if prize_pot == expected_pot:
            print("SUCCESS: Prize pot calculation is correct.")
        else:
            print(f"FAILURE: Prize pot calculation is incorrect. Expected {expected_pot}, got {prize_pot}")

if __name__ == "__main__":
    test_prize_pot()
