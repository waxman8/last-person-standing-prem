from datetime import datetime, timedelta
from sqlmodel import select, and_
from database import get_session
from models import User, Gameweek, Fixture, Pick
import api_client

def sync_fixtures_logic(session):
    """Core logic to fetch and update fixtures, and process live results."""
    matches = api_client.get_pl_fixtures()
    
    current_gw_num = api_client.get_current_gameweek_number()
    
    # Check if a current gameweek already exists to avoid overriding it
    existing_current_gw = session.exec(select(Gameweek).where(Gameweek.is_current == True)).first()
    
    # Update Gameweeks and Fixtures
    for m in matches:
        gw_id = m['matchday']
        kickoff = datetime.fromisoformat(m['utcDate'].replace('Z', '+00:00')).replace(tzinfo=None)
        
        # Upsert Gameweek
        gw = session.get(Gameweek, gw_id)
        if not gw:
            is_curr = (gw_id == current_gw_num) if not existing_current_gw else False
            gw = Gameweek(id=gw_id, deadline=kickoff, is_current=is_curr)
            session.add(gw)
        else:
            if kickoff < gw.deadline:
                gw.deadline = kickoff
            # Only update is_current if no gameweek is currently set as current
            if not existing_current_gw:
                gw.is_current = (gw_id == current_gw_num)
        
        # Upsert Fixture
        fix = session.get(Fixture, m['id'])
        if not fix:
            fix = Fixture(
                id=m['id'],
                gameweek_id=gw_id,
                home_team=m['homeTeam']['name'],
                away_team=m['awayTeam']['name'],
                kickoff_time=kickoff,
                status=m['status']
            )
            session.add(fix)
        else:
            fix.status = m['status']
            fix.kickoff_time = kickoff

        # Update scores if available in API
        score_data = m.get('score') or {}
        ft_score = score_data.get('fullTime') or {}
        home_score = ft_score.get('home')
        away_score = ft_score.get('away')

        if home_score is not None:
            # Use our established current gameweek to determine if a match is historic
            # if no current GW exists yet, fall back to the API suggestion
            ref_gw_id = existing_current_gw.id if existing_current_gw else current_gw_num
            is_historic = gw_id < ref_gw_id
            if not is_historic or fix.home_score is None:
                fix.home_score = home_score
                fix.away_score = away_score
                if fix.home_score > fix.away_score:
                    fix.winner = fix.home_team
                elif fix.away_score > fix.home_score:
                    fix.winner = fix.away_team
                else:
                    fix.winner = "DRAW"
    
    session.commit()
    
    # Live Processing
    current_gw = session.exec(select(Gameweek).where(Gameweek.is_current == True)).first()
    if current_gw:
        picks = session.exec(select(Pick).where(Pick.gameweek_id == current_gw.id)).all()
        for pick in picks:
            user = session.get(User, pick.user_id)
            if not user or not user.is_active or user.is_admin:
                continue
            
            fixture = session.exec(select(Fixture).where(
                and_(
                    Fixture.gameweek_id == current_gw.id,
                    (Fixture.home_team == pick.team_name) | (Fixture.away_team == pick.team_name)
                )
            )).first()
            
            if fixture and fixture.status == 'FINISHED':
                if fixture.winner != pick.team_name:
                    user.is_active = False
                    session.add(user)
        
        session.commit()
    return {"message": "Fixtures synced and live results applied"}
