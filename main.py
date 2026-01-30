from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from typing import List, Optional
from jose import JWTError, jwt
from sqlmodel import select, and_

from database import init_db, get_session
from models import User, Gameweek, Fixture, Pick
import api_client

# Security Constants
SECRET_KEY = "super-secret-key-change-this"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7 # 1 week

app = FastAPI(title="Last Man Standing")

# OAuth2 context
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")

@app.on_event("startup")
def on_startup():
    init_db()

# --- Auth Helpers ---
def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

async def get_current_user(token: str = Depends(oauth2_scheme), session: Session = Depends(get_session)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        pin: str = payload.get("sub")
        if pin is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
    
    user = session.exec(select(User).where(User.pin == pin)).first()
    if user is None:
        raise credentials_exception
    return user

async def get_admin_user(current_user: User = Depends(get_current_user)):
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")
    return current_user

# --- Routes ---

@app.post("/login")
async def login(form_data: OAuth2PasswordRequestForm = Depends(), session: Session = Depends(get_session)):
    # In this app, username is ignored, password is the PIN
    user = session.exec(select(User).where(User.pin == form_data.password)).first()
    if not user:
        raise HTTPException(status_code=400, detail="Invalid PIN")
    
    access_token = create_access_token(data={"sub": user.pin})
    return {"access_token": access_token, "token_type": "bearer"}

@app.get("/me")
async def read_users_me(current_user: User = Depends(get_current_user)):
    return current_user

# --- Admin Routes ---

@app.post("/admin/users", response_model=User)
async def create_user(user_in: User, admin: User = Depends(get_admin_user), session: Session = Depends(get_session)):
    session.add(user_in)
    session.commit()
    session.refresh(user_in)
    return user_in

@app.get("/admin/users", response_model=List[User])
async def list_users(admin: User = Depends(get_admin_user), session: Session = Depends(get_session)):
    return session.exec(select(User)).all()

@app.delete("/admin/users/{user_id}")
async def delete_user(user_id: int, admin: User = Depends(get_admin_user), session: Session = Depends(get_session)):
    user = session.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user.is_admin:
        raise HTTPException(status_code=400, detail="Cannot delete admin user")
    
    # Delete user's picks first
    picks = session.exec(select(Pick).where(Pick.user_id == user_id)).all()
    for pick in picks:
        session.delete(pick)
    
    session.delete(user)
    session.commit()
    return {"message": "User deleted successfully"}

@app.post("/admin/sync-fixtures")
async def sync_fixtures(admin: User = Depends(get_admin_user), session: Session = Depends(get_session)):
    """Only fetches and updates fixtures and gameweek deadlines."""
    try:
        matches = api_client.get_pl_fixtures()
        if not matches:
            raise Exception("No matches returned from API")
        
        current_gw_num = api_client.get_current_gameweek_number()
        
        # Update Gameweeks and Fixtures
        for m in matches:
            gw_id = m['matchday']
            # Convert to naive UTC datetime for database compatibility
            kickoff = datetime.fromisoformat(m['utcDate'].replace('Z', '+00:00')).replace(tzinfo=None)
            
            # Upsert Gameweek
            gw = session.get(Gameweek, gw_id)
            if not gw:
                gw = Gameweek(id=gw_id, deadline=kickoff, is_current=(gw_id == current_gw_num))
                session.add(gw)
            else:
                # Only update deadline if it's earlier
                if kickoff < gw.deadline:
                    gw.deadline = kickoff
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
                is_historic = gw_id < current_gw_num
                # Only update historic weeks if we don't have scores locally yet
                # For current/future weeks, always update to catch latest results
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
        return {"message": "Fixtures synced successfully"}
    except Exception as e:
        # Log the error for debugging
        print(f"Sync error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/admin/apply-results/{gw_id}")
async def apply_results(gw_id: int, admin: User = Depends(get_admin_user), session: Session = Depends(get_session)):
    """Resolves results for a specific gameweek."""
    gw = session.get(Gameweek, gw_id)
    if not gw:
        raise HTTPException(status_code=404, detail="Gameweek not found")
    
    if gw.is_processed:
        raise HTTPException(status_code=400, detail="Gameweek already processed")

    # Check if all fixtures are finished or postponed
    fixtures = session.exec(select(Fixture).where(Fixture.gameweek_id == gw.id)).all()
    if not all(f.status in ['FINISHED', 'POSTPONED', 'CANCELLED'] for f in fixtures):
        # Allow processing if the admin really wants to, but maybe warn?
        # For now, let's stick to the rule but allow it if at least some are finished.
        finished_or_postponed = [f for f in fixtures if f.status in ['FINISHED', 'POSTPONED', 'CANCELLED']]
        if not finished_or_postponed:
            raise HTTPException(status_code=400, detail="No fixtures are finished yet for this gameweek")

    # Resolve players
    picks = session.exec(select(Pick).where(Pick.gameweek_id == gw.id)).all()
    for pick in picks:
        user = session.get(User, pick.user_id)
        if not user or not user.is_active: continue
        
        # Find the fixture for this team
        fixture = next((f for f in fixtures if f.home_team == pick.team_name or f.away_team == pick.team_name), None)
        
        if not fixture:
            continue
        
        if fixture.status == 'POSTPONED' or fixture.status == 'CANCELLED':
            # Automatically through for now (common LMS rule)
            continue
        elif fixture.status == 'FINISHED':
            if fixture.winner == pick.team_name:
                # Through
                continue
            else:
                # Out
                user.is_active = False
                session.add(user)
    
    # Eliminate players who didn't pick
    active_users = session.exec(select(User).where(and_(User.is_active == True, User.is_admin == False))).all()
    for user in active_users:
        user_pick = session.exec(select(Pick).where(and_(Pick.user_id == user.id, Pick.gameweek_id == gw.id))).first()
        if not user_pick:
            user.is_active = False
            session.add(user)
    
    gw.is_processed = True
    session.add(gw)

    # Roll over: Set next gameweek as current if it exists
    next_gw = session.get(Gameweek, gw_id + 1)
    if next_gw:
        gw.is_current = False
        next_gw.is_current = True
        session.add(next_gw)

    session.commit()
    
    return {"message": f"Gameweek {gw_id} processed successfully. Rolled over to GW {gw_id + 1 if next_gw else gw_id}."}

@app.get("/admin/gameweeks")
async def get_gameweeks(admin: User = Depends(get_admin_user), session: Session = Depends(get_session)):
    return session.exec(select(Gameweek).order_by(Gameweek.id)).all()

@app.get("/admin/fixtures/{gw_id}")
async def get_gw_fixtures(gw_id: int, admin: User = Depends(get_admin_user), session: Session = Depends(get_session)):
    return session.exec(select(Fixture).where(Fixture.gameweek_id == gw_id).order_by(Fixture.kickoff_time)).all()

@app.get("/admin/picks/{gw_id}")
async def get_admin_picks(gw_id: int, admin: User = Depends(get_admin_user), session: Session = Depends(get_session)):
    users = session.exec(select(User).where(User.is_admin == False)).all()
    picks = session.exec(select(Pick).where(Pick.gameweek_id == gw_id)).all()
    picks_map = {p.user_id: p for p in picks}
    
    results = []
    for u in users:
        results.append({
            "user_id": u.id,
            "user_name": u.name,
            "is_active": u.is_active,
            "team_name": picks_map[u.id].team_name if u.id in picks_map else None
        })
    return results

@app.post("/admin/picks/{gw_id}/batch")
async def batch_update_admin_picks(gw_id: int, picks_in: List[dict], admin: User = Depends(get_admin_user), session: Session = Depends(get_session)):
    # Get all fixtures for this GW to validate teams
    fixtures = session.exec(select(Fixture).where(Fixture.gameweek_id == gw_id)).all()
    valid_teams = set()
    for f in fixtures:
        valid_teams.add(f.home_team)
        valid_teams.add(f.away_team)

    for p in picks_in:
        user_id = p.get('user_id')
        team_name = p.get('team_name')
        
        if team_name and team_name not in valid_teams:
            continue # Or raise error, but skipping invalid teams in batch is safer
        
        existing_pick = session.exec(select(Pick).where(and_(Pick.user_id == user_id, Pick.gameweek_id == gw_id))).first()
        
        if not team_name:
            if existing_pick:
                session.delete(existing_pick)
        else:
            if existing_pick:
                if existing_pick.team_name != team_name:
                    existing_pick.team_name = team_name
                    existing_pick.timestamp = datetime.utcnow()
            else:
                new_pick = Pick(user_id=user_id, gameweek_id=gw_id, team_name=team_name)
                session.add(new_pick)
    
    session.commit()
    return {"message": "Picks updated successfully"}

# --- Player Routes ---

@app.get("/fixtures")
async def get_current_fixtures(session: Session = Depends(get_session)):
    current_gw = session.exec(select(Gameweek).where(Gameweek.is_current == True)).first()
    if not current_gw:
        return []
    fixtures = session.exec(select(Fixture).where(Fixture.gameweek_id == current_gw.id).order_by(Fixture.kickoff_time)).all()
    return [{
        "id": f.id,
        "home_team": f.home_team,
        "away_team": f.away_team,
        "kickoff_time": f.kickoff_time,
        "status": f.status,
        "gameweek": {
            "id": current_gw.id,
            "deadline": current_gw.deadline
        }
    } for f in fixtures]

@app.post("/picks")
async def make_pick(team_name: str, current_user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    if not current_user.is_active:
        raise HTTPException(status_code=400, detail="You are eliminated")
    
    current_gw = session.exec(select(Gameweek).where(Gameweek.is_current == True)).first()
    if not current_gw:
        raise HTTPException(status_code=400, detail="No active gameweek")
    
    if datetime.utcnow() > current_gw.deadline:
        raise HTTPException(status_code=400, detail="Deadline passed")
    
    # Check if team already used
    prev_pick = session.exec(select(Pick).where(and_(Pick.user_id == current_user.id, Pick.team_name == team_name))).first()
    if prev_pick:
        raise HTTPException(status_code=400, detail="Team already used")
    
    # Upsert pick
    # Check if team is in current fixtures
    fixtures = session.exec(select(Fixture).where(Fixture.gameweek_id == current_gw.id)).all()
    valid_teams = set()
    for f in fixtures:
        valid_teams.add(f.home_team)
        valid_teams.add(f.away_team)
    
    if team_name not in valid_teams:
        raise HTTPException(status_code=400, detail="Invalid team selection")

    # Upsert pick
    existing_pick = session.exec(select(Pick).where(and_(Pick.user_id == current_user.id, Pick.gameweek_id == current_gw.id))).first()
    if existing_pick:
        existing_pick.team_name = team_name
        existing_pick.timestamp = datetime.utcnow()
    else:
        new_pick = Pick(user_id=current_user.id, gameweek_id=current_gw.id, team_name=team_name)
        session.add(new_pick)
    
    session.commit()
    return {"message": "Pick saved"}

@app.get("/public/standings")
async def get_public_standings(session: Session = Depends(get_session)):
    users = session.exec(select(User).where(User.is_admin == False)).all()
    current_gw = session.exec(select(Gameweek).where(Gameweek.is_current == True)).first()
    
    results = []
    for u in users:
        pick = None
        if current_gw:
            pick_obj = session.exec(select(Pick).where(and_(Pick.user_id == u.id, Pick.gameweek_id == current_gw.id))).first()
            if pick_obj:
                pick = pick_obj.team_name
        
        results.append({
            "name": u.name,
            "is_active": u.is_active,
            "current_pick": pick
        })
    return {
        "gw_id": current_gw.id if current_gw else None,
        "standings": results
    }

@app.get("/standings")
async def get_standings(current_user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    users = session.exec(select(User).where(User.is_admin == False)).all()
    current_gw = session.exec(select(Gameweek).where(Gameweek.is_current == True)).first()
    
    results = []
    for u in users:
        pick = None
        if current_gw:
            pick_obj = session.exec(select(Pick).where(and_(Pick.user_id == u.id, Pick.gameweek_id == current_gw.id))).first()
            if pick_obj:
                # Always show own pick, show others only if deadline passed
                if u.id == current_user.id or datetime.utcnow() > current_gw.deadline:
                    pick = pick_obj.team_name
        
        results.append({
            "name": u.name,
            "is_active": u.is_active,
            "current_pick": pick
        })
    return results

@app.get("/history")
async def get_user_history(current_user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    # Get all picks for the user, ordered by gameweek
    picks = session.exec(select(Pick).where(Pick.user_id == current_user.id).order_by(Pick.gameweek_id)).all()
    
    history = []
    for pick in picks:
        gw = session.get(Gameweek, pick.gameweek_id)
        if not gw: continue

        # Find the fixture for this team in this gameweek
        fixture = session.exec(select(Fixture).where(
            and_(
                Fixture.gameweek_id == pick.gameweek_id,
                (Fixture.home_team == pick.team_name) | (Fixture.away_team == pick.team_name)
            )
        )).first()
        
        outcome = "Pending"
        if fixture:
            if fixture.status == 'FINISHED':
                outcome = "WON" if fixture.winner == pick.team_name else "LOST"
            elif fixture.status in ['POSTPONED', 'CANCELLED']:
                outcome = "THROUGH (Postponed)" if gw.is_processed else "POSTPONED"
            elif fixture.status == 'IN_PLAY':
                outcome = "In Play"
        
        history.append({
            "gameweek_id": pick.gameweek_id,
            "team_name": pick.team_name,
            "outcome": outcome,
            "is_processed": gw.is_processed
        })
    
    return history

# Serve static files (Frontend)
app.mount("/", StaticFiles(directory="frontend", html=True), name="frontend")
