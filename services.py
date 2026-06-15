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
                
                kickoff = datetime.fromisoformat(m['utcDate'].replace('Z', '+00:00')).replace(tzinfo=None)
                
                # Upsert Gameweek
                gw = session.exec(
                    select(Gameweek).where(
                        and_(Gameweek.competition_id == comp.id, Gameweek.number == gw_number)
                    )
                ).first()
                
                if not gw:
                    is_curr = (gw_number == current_gw_num) if not existing_current_gw else False
                    gw = Gameweek(number=gw_number, competition_id=comp.id, deadline=kickoff, is_current=is_curr)
                    session.add(gw)
                    session.flush() # Get ID
                else:
                    if not gw.is_current and not gw.is_processed and m['status'] not in ['FINISHED', 'POSTPONED', 'CANCELLED']:
                        if kickoff < gw.deadline:
                            gw.deadline = kickoff
                    if not existing_current_gw:
                        gw.is_current = (gw_number == current_gw_num)
                
                # Upsert Fixture
                home_team_data = m.get('homeTeam', {})
                away_team_data = m.get('awayTeam', {})
                home_team = home_team_data.get('name')
                away_team = away_team_data.get('name')
                
                # LOG TEAM INFO FOR MAPPING
                if home_team:
                    logger.info(f"TEAM_MAPPING: {home_team} -> {home_team_data.get('crest')}")
                if away_team:
                    logger.info(f"TEAM_MAPPING: {away_team} -> {away_team_data.get('crest')}")

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
                    fix.home_team_crest = home_team_data.get('crest')
                    fix.away_team_crest = away_team_data.get('crest')

                # Process results
                score_data = m.get('score') or {}
                winner_code = score_data.get('winner') # HOME_TEAM, AWAY_TEAM, DRAW
                
                if winner_code:
                    if winner_code == "HOME_TEAM":
                        fix.winner = fix.home_team
                    elif winner_code == "AWAY_TEAM":
                        fix.winner = fix.away_team
                    else:
                        fix.winner = "DRAW"
                    
                    # Update scores
                    ft = score_data.get('fullTime') or {}
                    fix.home_score = ft.get('home')
                    fix.away_score = ft.get('away')

            session.commit()
            
            # Live Processing for this competition
            process_live_results(session, comp)
            
        except Exception as e:
            logger.error(f"Error syncing {comp.code}: {str(e)}", exc_info=True)
            continue

    return {"message": "Fixtures synced and live results applied for all competitions"}

def stage_to_number(stage: str) -> int:
    """Maps tournament stages to a numeric sequence."""
    mapping = {
        'GROUP_STAGE': 1, # Should be handled by matchday usually
        'ROUND_OF_32': 4,
        'ROUND_OF_16': 5,
        'QUARTER_FINALS': 6,
        'SEMI_FINALS': 7,
        'FINAL': 8,
        'THIRD_PLACE': 9
    }
    return mapping.get(stage, 10)

def check_rebuy_eligibility(competition_code: str, stage: str) -> bool:
    """Centralized logic for competition-specific re-buy eligibility."""
    if competition_code == "WC":
        # Re-buy allowed for Group Stage, R32, and R16 (to enter R8)
        # Rule: No re-buy after R8 (Quarter Finals)
        return stage in ['GROUP_STAGE', 'ROUND_OF_32', 'ROUND_OF_16']
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
            if fixture.winner != pick.team_name:
                status.status = 'OUT'
                status.is_active = False
                # Eligibility for re-buy based on centralized rules
                if check_rebuy_eligibility(competition.code, fixture.stage):
                    status.eligible_for_rebuy = True
                session.add(status)
    
    session.commit()
