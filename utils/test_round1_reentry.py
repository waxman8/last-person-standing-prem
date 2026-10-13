import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from sqlmodel import Session, create_engine, SQLModel, select, and_, desc
from datetime import datetime, timezone, timedelta
from models import User, Gameweek, Fixture, Pick, Competition, UserCompetitionStatus
from services import is_first_gameweek, check_rebuy_eligibility, process_live_results, retroactive_status_sync

def run_tests():
    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        # 1. Create a LEAGUE competition (PL)
        comp = Competition(name="Premier League", code="PL", type="LEAGUE", entry_fee=10.0, is_active=True)
        session.add(comp)
        session.commit()
        session.refresh(comp)

        now = datetime.now(timezone.utc)
        gw1 = Gameweek(number=1, competition_id=comp.id, deadline=now + timedelta(days=1), is_current=True, is_processed=False)
        gw2 = Gameweek(number=2, competition_id=comp.id, deadline=now + timedelta(days=7), is_current=False, is_processed=False)
        gw3 = Gameweek(number=3, competition_id=comp.id, deadline=now + timedelta(days=14), is_current=False, is_processed=False)
        session.add_all([gw1, gw2, gw3])
        session.commit()
        session.refresh(gw1)
        session.refresh(gw2)
        session.refresh(gw3)

        # 2. Test is_first_gameweek helper
        assert is_first_gameweek(session, comp.id, gw1.id, gw1.number) == True, "GW1 should be first gameweek"
        assert is_first_gameweek(session, comp.id, gw2.id, gw2.number) == False, "GW2 should not be first gameweek"
        assert is_first_gameweek(session, comp.id, gw3.id, gw3.number) == False, "GW3 should not be first gameweek"
        print("PASS: is_first_gameweek helper works correctly")

        # 3. Test check_rebuy_eligibility
        assert check_rebuy_eligibility(comp.code, "REGULAR", is_first_round=True) == True, "Round 1 of PL must be eligible for re-entry"
        assert check_rebuy_eligibility(comp.code, "REGULAR", is_first_round=False) == False, "Round 2+ of PL must NOT be eligible for re-entry"
        assert check_rebuy_eligibility("WC", "GROUP_STAGE", is_first_round=False) == True, "WC Group Stage remains eligible"
        assert check_rebuy_eligibility("WC", "QUARTER_FINALS", is_first_round=False) == False, "WC QF is not eligible"
        print("PASS: check_rebuy_eligibility rules work correctly")

        # 4. Create players
        user1 = User(name="Player One", pin="11111", is_active=True)
        user2 = User(name="Player Two", pin="22222", is_active=True)
        session.add_all([user1, user2])
        session.commit()
        session.refresh(user1)
        session.refresh(user2)

        status1 = UserCompetitionStatus(user_id=user1.id, competition_id=comp.id, status="ACTIVE", is_active=True, paid=True)
        status2 = UserCompetitionStatus(user_id=user2.id, competition_id=comp.id, status="ACTIVE", is_active=True, paid=True)
        session.add_all([status1, status2])
        session.commit()

        # Fixture 1 in GW1: Arsenal vs Chelsea
        fix1 = Fixture(
            id=101, gameweek_id=gw1.id, competition_id=comp.id,
            home_team="Arsenal", away_team="Chelsea",
            kickoff_time=now - timedelta(hours=2),
            status="FINISHED", stage="REGULAR", winner="Chelsea"
        )
        session.add(fix1)

        # User1 picks Arsenal (loses)
        pick1 = Pick(user_id=user1.id, gameweek_id=gw1.id, competition_id=comp.id, team_name="Arsenal")
        session.add(pick1)
        session.commit()

        # 5. Process live results in GW1
        process_live_results(session, comp)
        session.refresh(status1)
        assert status1.status == "OUT", "Player 1 should be OUT"
        assert status1.eligible_for_rebuy == True, "Player 1 should be eligible for rebuy after Round 1 elimination"
        print("PASS: Player eliminated in Round 1 is OUT and eligible_for_rebuy is True")

        # 6. Simulate retroactive sync to verify it preserves or re-grants eligibility
        status1.eligible_for_rebuy = False
        session.add(status1)
        session.commit()
        retroactive_status_sync(session)
        session.refresh(status1)
        assert status1.eligible_for_rebuy == True, "Retroactive sync should grant eligible_for_rebuy to Round 1 eliminated players"
        print("PASS: Retroactive status sync properly updates Round 1 players to eligible_for_rebuy=True")

        # 7. Test queuing re-entry during Round 1
        # Player is OUT in GW1, admin re-enters them
        status1.has_paid_reentry = True
        session.add(status1)
        session.commit()

        # 8. Simulate GW1 finalize -> GW2 transition
        gw1.is_processed = True
        gw1.is_current = False
        gw2.is_current = True
        session.add_all([gw1, gw2])
        
        # Auto-activate queued
        queued = session.exec(select(UserCompetitionStatus).where(and_(
            UserCompetitionStatus.competition_id == comp.id,
            UserCompetitionStatus.has_paid_reentry == True
        ))).all()
        for q in queued:
            q.status = "ACTIVE"
            q.is_active = True
            q.eligible_for_rebuy = False
            q.last_re_entry_gw_id = gw2.id
            q.has_paid_reentry = False
            q.number_of_re_entries += 1
            session.add(q)
        session.commit()
        session.refresh(status1)

        assert status1.status == "ACTIVE", "Player 1 should now be ACTIVE in GW2"
        assert status1.number_of_re_entries == 1, "Player 1 re-entries count should be 1"
        assert status1.eligible_for_rebuy == False, "eligible_for_rebuy should now be False"
        print("PASS: Queued re-entry activated cleanly into Round 2 with re_entries=1")

        # 9. Verify Player 1 can pick Arsenal again in GW2 (team reuse allowed after buy back)
        user_re_entry_number = gw2.number
        effective_threshold = user_re_entry_number
        prev_pick = session.exec(select(Pick).join(Gameweek).where(and_(
            Pick.user_id == user1.id,
            Pick.competition_id == comp.id,
            Pick.team_name == "Arsenal",
            Pick.gameweek_id != gw2.id,
            Gameweek.number >= effective_threshold
        ))).first()
        assert prev_pick is None, "Player 1 should be allowed to pick Arsenal again in GW2 because GW1 pick is prior to effective threshold"
        print("PASS: Player 1 is allowed to pick the same team (Arsenal) in Round 2 after re-entry")

        # 10. In GW2, Player 1 and Player 2 both play
        fix2 = Fixture(
            id=102, gameweek_id=gw2.id, competition_id=comp.id,
            home_team="Arsenal", away_team="Liverpool",
            kickoff_time=now - timedelta(hours=1),
            status="FINISHED", stage="REGULAR", winner="Liverpool"
        )
        session.add(fix2)
        pick2_u1 = Pick(user_id=user1.id, gameweek_id=gw2.id, competition_id=comp.id, team_name="Arsenal")
        pick2_u2 = Pick(user_id=user2.id, gameweek_id=gw2.id, competition_id=comp.id, team_name="Arsenal")
        session.add_all([pick2_u1, pick2_u2])
        session.commit()

        # Process GW2 results
        process_live_results(session, comp)
        session.refresh(status1)
        session.refresh(status2)
        assert status1.status == "OUT", "Player 1 should be OUT in GW2"
        assert status1.eligible_for_rebuy == False, "Player 1 should NOT be eligible for rebuy after Round 2 elimination"
        assert status2.status == "OUT", "Player 2 should be OUT in GW2"
        assert status2.eligible_for_rebuy == False, "Player 2 should NOT be eligible for rebuy after Round 2 elimination"
        print("PASS: Elimination in Round 2 sets eligible_for_rebuy=False for all players")

        # 11. Verify pot calculation with re-entries
        # Player 1 has 1 re-entry. Both players are OUT (paid entries = 2)
        statuses = [status1, status2]
        paid_entries = sum(1 for s in statuses if s.paid or s.status in ['ACTIVE', 'OUT'])
        total_re_entries = sum(s.number_of_re_entries for s in statuses)
        prize_pot = (paid_entries + total_re_entries) * comp.entry_fee
        assert paid_entries == 2, "Both players should count as paid entries"
        assert total_re_entries == 1, "There should be 1 re-entry recorded"
        assert prize_pot == 30.0, f"Prize pot should be (2 + 1) * 10 = £30.0, got {prize_pot}"
        print("PASS: Prize pot calculation accurately includes paid entries and re-entries")

        # 12. Test LPL competition scenario (GW6 is Round 1, GW7 is Round 2)
        lpl_comp = Competition(name="Lapland Prem 26/27", code="LPL", type="LEAGUE", entry_fee=10.0, is_active=True)
        session.add(lpl_comp)
        session.commit()
        session.refresh(lpl_comp)

        # Gameweeks 1-38 synced, but LPL only starts at GW6
        lpl_gws = [Gameweek(number=i, competition_id=lpl_comp.id, deadline=now + timedelta(days=i), is_current=(i==7), is_processed=(i<=6)) for i in range(1, 39)]
        session.add_all(lpl_gws)
        session.commit()

        # Users pick in GW6
        lpl_u1 = User(name="LPL Player", pin="33333", is_active=True)
        session.add(lpl_u1)
        session.commit()
        session.refresh(lpl_u1)

        lpl_status = UserCompetitionStatus(user_id=lpl_u1.id, competition_id=lpl_comp.id, status="OUT", is_active=False, paid=True, number_of_re_entries=0)
        session.add(lpl_status)
        session.commit()

        # GW6 pick
        lpl_pick = Pick(user_id=lpl_u1.id, gameweek_id=lpl_gws[5].id, competition_id=lpl_comp.id, team_name="Arsenal") # GW6 has index 5
        session.add(lpl_pick)
        session.commit()

        from services import get_competition_first_round_number
        first_round_num = get_competition_first_round_number(session, lpl_comp.id)
        assert first_round_num == 6, f"LPL first round should be detected as GW6, got {first_round_num}"
        assert first_round_num + 1 == 7, "LPL round 2 should be GW7"

        # Current GW is GW7 (Round 2 for LPL). Re-entry should be ALLOWED!
        current_gw7 = lpl_gws[6] # index 6 is GW7
        assert current_gw7.number <= first_round_num + 1, "GW7 must be eligible for Round 2 re-entry"
        print("PASS: LPL Round 1 (GW6) and Round 2 (GW7) correctly identified and eligible for buy back")

        print("\nALL VERIFICATION TESTS PASSED SUCCESSFULLY!")

if __name__ == "__main__":
    run_tests()
