from datetime import datetime, timedelta, timezone
from sqlmodel import select, and_
from database import get_session
from models import User, Gameweek, Fixture, Pick, Competition, UserCompetitionStatus
import api_client
import logging
logger = logging.getLogger(__name__)

def sync_fixtures_logic(session):
    """Core logic to fetch and update fixtures for all active competitions."""
    competitions = session.exec(select(Competition).where(Competition.is_active == True)).all()
    logger.info(f"Starting sync for {len(competitions)} competitions")
    
    for comp in competitions:
        try:
            logger.info(f"Syncing competition: {comp.name} ({comp.code})")
            matches = api_client.get_fixtures(comp.code)
            logger.info(f"Fetched {len(matches)} matches for {comp.code}")
            current_gw_num = api_client.get_current_matchday(comp.code)
            logger.info(f"Current matchday for {comp.code}: {current_gw_num}")
            
            existing_current_gw = session.exec(
                select(Gameweek).where(
                    and_(Gameweek.competition_id == comp.id, Gameweek.is_current == True)
                )
            ).first()
            
            for m in matches:
                # Map stage/matchday
                stage = m.get('stage', 'REGULAR')
                matchday = m.get('matchday')
                
                # In tournaments, matchday might be null for knockouts
                # We need a unique way to identify the "Gameweek" for our app
                # For simplicity, we'll use a sequence or map stages to numbers
                gw_number = matchday if matchday else stage_to_number(stage)
                
                if gw_number is None:
                    logger.info(f"Skipping fixture {m['id']} as stage '{stage}' is not mapped/allowed")
                    continue
                
                kickoff = datetime.fromisoformat(m['utcDate'].replace('Z', '+00:00'))
                
                # Upsert Gameweek
                gw = session.exec(
                    select(Gameweek).where(
                        and_(Gameweek.competition_id == comp.id, Gameweek.number == gw_number)
                    )
                ).first()
                
                if not gw:
                    is_curr = (gw_number == current_gw_num) if (not existing_current_gw or existing_current_gw.is_processed) else False
                    gw = Gameweek(number=gw_number, competition_id=comp.id, deadline=kickoff, is_current=is_curr)
                    if is_curr and existing_current_gw and existing_current_gw.id != gw.id:
                        existing_current_gw.is_current = False
                        session.add(existing_current_gw)
                    session.add(gw)
                    session.flush() # Get ID
                else:
                    if not gw.is_current and not gw.is_processed and m['status'] not in ['FINISHED', 'POSTPONED', 'CANCELLED']:
                        if kickoff < gw.deadline:
                            gw.deadline = kickoff
                    if not existing_current_gw or existing_current_gw.is_processed:
                        is_new_curr = (gw_number == current_gw_num)
                        if is_new_curr and not gw.is_current:
                            gw.is_current = True
                            if existing_current_gw and existing_current_gw.id != gw.id:
                                existing_current_gw.is_current = False
                                session.add(existing_current_gw)
                
                # Upsert Fixture
                home_team_data = m.get('homeTeam', {})
                away_team_data = m.get('awayTeam', {})
                home_team = home_team_data.get('name')
                away_team = away_team_data.get('name')
                
                if not home_team or not away_team:
                    logger.warning(f"Skipping fixture {m['id']} as teams are not yet determined")
                    continue

                fix = session.get(Fixture, m['id'])
                if not fix:
                    fix = Fixture(
                        id=m['id'],
                        gameweek_id=gw.id,
                        competition_id=comp.id,
                        home_team=home_team,
                        away_team=away_team,
                        home_team_crest=home_team_data.get('crest'),
                        away_team_crest=away_team_data.get('crest'),
                        kickoff_time=kickoff,
                        status=m['status'],
                        stage=stage
                    )
                    session.add(fix)
                else:
                    fix.status = m['status']
                    fix.kickoff_time = kickoff
                    fix.stage = stage
                    fix.gameweek_id = gw.id # Update in case mapping changed (e.g. Stage 10 -> 4)
                    fix.competition_id = comp.id # Ensure it's linked to the current active competition
                    fix.home_team_crest = home_team_data.get('crest')
                    fix.away_team_crest = away_team_data.get('crest')

                # Process results
                score_data = m.get('score') or {}
                winner_code = score_data.get('winner') # HOME_TEAM, AWAY_TEAM, DRAW
                ft = score_data.get('fullTime') or {}
                home_score = ft.get('home')
                away_score = ft.get('away')

                # Fallback: Derive winner if match is FINISHED but API hasn't set winner yet
                if m.get('status') == 'FINISHED' and not winner_code:
                    if home_score is not None and away_score is not None:
                        if home_score > away_score:
                            winner_code = "HOME_TEAM"
                        elif away_score > home_score:
                            winner_code = "AWAY_TEAM"
                        else:
                            winner_code = "DRAW"
                
                if winner_code:
                    if winner_code == "HOME_TEAM":
                        fix.winner = fix.home_team
                    elif winner_code == "AWAY_TEAM":
                        fix.winner = fix.away_team
                    else:
                        fix.winner = "DRAW"
                    
                    # Update scores
                    fix.home_score = home_score
                    fix.away_score = away_score

            session.commit()
            
            # Live Processing for this competition
            process_live_results(session, comp)
            
        except Exception as e:
            logger.error(f"Error syncing {comp.code}: {str(e)}", exc_info=True)
            continue

    return {"message": "Fixtures synced and live results applied for all competitions"}

def stage_to_number(stage: str) -> int | None:
    """Maps tournament stages to a numeric sequence. Returns None if stage should be excluded."""
    mapping = {
        'GROUP_STAGE': 1, # Should be handled by matchday usually
        'ROUND_OF_32': 4,
        'LAST_32': 4,
        'ROUND_OF_16': 5,
        'LAST_16': 5,
        'QUARTER_FINALS': 6,
        'SEMI_FINALS': 7,
        'FINAL': 8,
    }
    return mapping.get(stage)

def check_rebuy_eligibility(competition_code: str, stage: str) -> bool:
    """Centralized logic for competition-specific re-buy eligibility."""
    if competition_code == "WC":
        # Re-buy allowed for Group Stage, R32, and R16 (to enter R8)
        # Rule: No re-buy after R8 (Quarter Finals)
        return stage in ['GROUP_STAGE', 'ROUND_OF_32', 'LAST_32', 'ROUND_OF_16', 'LAST_16']
    return False

def process_live_results(session, competition):
    """Processes picks for the current gameweek of a competition."""
    current_gw = session.exec(
        select(Gameweek).where(
            and_(Gameweek.competition_id == competition.id, Gameweek.is_current == True)
        )
    ).first()
    
    if not current_gw:
        return

    picks = session.exec(select(Pick).where(Pick.gameweek_id == current_gw.id)).all()
    for pick in picks:
        # Get competition-specific status
        status = session.exec(
            select(UserCompetitionStatus).where(
                and_(
                    UserCompetitionStatus.user_id == pick.user_id,
                    UserCompetitionStatus.competition_id == competition.id
                )
            )
        ).first()
        
        if not status or not status.is_active:
            continue
        
        fixture = session.exec(select(Fixture).where(
            and_(
                Fixture.gameweek_id == current_gw.id,
                (Fixture.home_team == pick.team_name) | (Fixture.away_team == pick.team_name)
            )
        )).first()
        
        if fixture and fixture.status == 'FINISHED':
            logger.info(f"DEBUG: Processing pick for user {pick.user_id}, team {pick.team_name}. Fixture {fixture.id} winner is {fixture.winner}")
            if fixture.winner != pick.team_name:
                logger.info(f"DEBUG: Marking user {pick.user_id} as OUT. Pick: {pick.team_name}, Winner: {fixture.winner}")
                status.status = 'OUT'
                status.is_active = False
                # Eligibility for re-buy based on centralized rules
                if check_rebuy_eligibility(competition.code, fixture.stage):
                    status.eligible_for_rebuy = True
                session.add(status)
    
    session.commit()

def retroactive_status_sync(session):
    """Retroactively updates player statuses for all finished matches in current gameweeks."""
    competitions = session.exec(select(Competition).where(Competition.is_active == True)).all()
    count = 0
    for comp in competitions:
        current_gw = session.exec(
            select(Gameweek).where(
                and_(Gameweek.competition_id == comp.id, Gameweek.is_current == True)
            )
        ).first()
        
        if not current_gw:
            continue

        picks = session.exec(select(Pick).where(Pick.gameweek_id == current_gw.id)).all()
        for pick in picks:
            status = session.exec(
                select(UserCompetitionStatus).where(
                    and_(
                        UserCompetitionStatus.user_id == pick.user_id,
                        UserCompetitionStatus.competition_id == comp.id
                    )
                )
            ).first()
            
            if not status:
                continue
            
            fixture = session.exec(select(Fixture).where(
                and_(
                    Fixture.gameweek_id == current_gw.id,
                    (Fixture.home_team == pick.team_name) | (Fixture.away_team == pick.team_name)
                )
            )).first()
            
            if fixture and fixture.status == 'FINISHED':
                if fixture.winner != pick.team_name:
                    if status.status != 'OUT':
                        logger.info(f"DEBUG RETRO: Marking user {pick.user_id} as OUT. Pick: {pick.team_name}, Winner: {fixture.winner}")
                        status.status = 'OUT'
                        status.is_active = False
                        if check_rebuy_eligibility(comp.code, fixture.stage):
                            status.eligible_for_rebuy = True
                        session.add(status)
                        count += 1
                    else:
                        # Even if they are already OUT, re-check eligibility in case code changed
                        if check_rebuy_eligibility(comp.code, fixture.stage):
                            if not status.eligible_for_rebuy:
                                status.eligible_for_rebuy = True
                                session.add(status)
                                count += 1
                else:
                    # If they won, make sure they are ACTIVE (in case of manual error override)
                    if status.status == 'OUT':
                        logger.info(f"DEBUG RETRO: Marking user {pick.user_id} as ACTIVE (Win). Pick: {pick.team_name}, Winner: {fixture.winner}")
                        status.status = 'ACTIVE'
                        status.is_active = True
                        status.eligible_for_rebuy = False
                        session.add(status)
                        count += 1
    
    session.commit()
    return count
