import asyncio
import logging
import random
import sys
from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from datetime import datetime, timedelta, timezone
from typing import List, Optional
from jose import JWTError, jwt
from sqlmodel import select, and_, desc

from database import init_db, get_session
from models import User, Gameweek, Fixture, Pick, Competition, UserCompetitionStatus
import api_client
from services import sync_fixtures_logic
from scheduler import fixture_scheduler_worker

# Security Constants
SECRET_KEY = "super-secret-key-change-this"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7 # 1 week
FIRST_GW_ID = 24

# Configure logging to match the uvicorn style
from uvicorn.logging import DefaultFormatter

handler = logging.StreamHandler(sys.stderr)
handler.setFormatter(DefaultFormatter('%(levelname)s:     %(message)s'))
logging.root.handlers = [handler]
logging.root.setLevel(logging.INFO)

logger = logging.getLogger(__name__)

app = FastAPI(title="Last Man Standing")

@app.middleware("http")
async def add_no_cache_header(request, call_next):
    response = await call_next(request)
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response

# OAuth2 context
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")

@app.on_event("startup")
async def on_startup():
    init_db()
    # Start the fixture scheduler in the background
    now = datetime.now().strftime("%d-%m-%Y %H:%M:%S")
    logger.info(f"{now} - scheduler - Fixture scheduler worker started")
    asyncio.create_task(fixture_scheduler_worker())

# --- Auth Helpers ---
def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
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
    if not user_in.pin:
        user_in.pin = "".join([str(random.randint(0, 9)) for _ in range(5)])
        
    session.add(user_in)
    session.commit()
    session.refresh(user_in)
    
    # Initialize competition status for all active competitions
    comps = session.exec(select(Competition).where(Competition.is_active == True)).all()
    for c in comps:
        status = UserCompetitionStatus(user_id=user_in.id, competition_id=c.id, status="PENDING", is_active=False, paid=False)
        session.add(status)
    session.commit()
    
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
    
    # Delete user's picks and statuses first
    picks = session.exec(select(Pick).where(Pick.user_id == user_id)).all()
    for pick in picks: session.delete(pick)
    
    statuses = session.exec(select(UserCompetitionStatus).where(UserCompetitionStatus.user_id == user_id)).all()
    for s in statuses: session.delete(s)
    
    session.delete(user)
    session.commit()
    return {"message": "User deleted successfully"}

@app.post("/admin/users/{user_id}/re-entry")
async def user_re_entry(user_id: int, competition_id: int = 2, admin: User = Depends(get_admin_user), session: Session = Depends(get_session)):
    status = session.exec(
        select(UserCompetitionStatus).where(
            and_(UserCompetitionStatus.user_id == user_id, UserCompetitionStatus.competition_id == competition_id)
        )
    ).first()
    
    if not status:
        raise HTTPException(status_code=404, detail="User status for this competition not found")
    
    current_gw = session.exec(
        select(Gameweek).where(and_(Gameweek.competition_id == competition_id, Gameweek.is_current == True))
    ).first()
    
    if not current_gw or (not current_gw.re_entry_allowed and not current_gw.is_rollover and not status.eligible_for_rebuy):
        raise HTTPException(status_code=400, detail="Re-entry or Rollover activation not allowed in the current stage")
    
    if status.status == "ACTIVE":
        raise HTTPException(status_code=400, detail="User is already active")
    
    status.status = "ACTIVE"
    status.eligible_for_rebuy = False
    
    if current_gw.is_rollover:
        status.number_of_rollovers += 1
    else:
        status.number_of_re_entries += 1
        
    status.paid = True
    session.add(status)
    session.commit()
    session.refresh(status)
    return status

@app.post("/admin/users/{user_id}/status")
async def update_user_status(user_id: int, new_status: str, competition_id: int = 2, admin: User = Depends(get_admin_user), session: Session = Depends(get_session)):
    if new_status not in ["PENDING", "ACTIVE", "OUT"]:
        raise HTTPException(status_code=400, detail="Invalid status")
        
    status = session.exec(
        select(UserCompetitionStatus).where(
            and_(UserCompetitionStatus.user_id == user_id, UserCompetitionStatus.competition_id == competition_id)
        )
    ).first()
    
    if not status:
        raise HTTPException(status_code=404, detail="User status for this competition not found")
    
    status.status = new_status
    status.is_active = (new_status == "ACTIVE")
    if new_status == "ACTIVE":
        status.paid = True
        
    session.add(status)
    session.commit()
    session.refresh(status)
    return status

@app.post("/admin/gameweeks/{gw_id}/trigger-rollover")
async def trigger_rollover(gw_id: int, admin: User = Depends(get_admin_user), session: Session = Depends(get_session)):
    gw = session.get(Gameweek, gw_id)
    if not gw: raise HTTPException(status_code=404, detail="Gameweek not found")
    gw.is_rollover = True
    session.add(gw)
    session.commit()
    return {"message": f"Rollover triggered for Gameweek {gw.number}. Please manually re-activate players who have bought back in."}

@app.post("/admin/sync-fixtures")
async def sync_fixtures(admin: User = Depends(get_admin_user), session: Session = Depends(get_session)):
    try:
        return sync_fixtures_logic(session)
    except Exception as e:
        logger.error(f"Sync error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/admin/apply-results/{gw_id}")
async def apply_results(gw_id: int, admin: User = Depends(get_admin_user), session: Session = Depends(get_session)):
    gw = session.get(Gameweek, gw_id)
    if not gw: raise HTTPException(status_code=404, detail="Gameweek not found")
    if gw.is_processed: raise HTTPException(status_code=400, detail="Gameweek already processed")

    comp = session.get(Competition, gw.competition_id)
    fixtures = session.exec(select(Fixture).where(Fixture.gameweek_id == gw.id)).all()
    all_finalized = all(f.status in ['FINISHED', 'POSTPONED', 'CANCELLED'] for f in fixtures)
    
    if not all_finalized:
        raise HTTPException(status_code=400, detail="Cannot finalize: some fixtures are still in play.")

    picks = session.exec(select(Pick).where(Pick.gameweek_id == gw.id)).all()
    for pick in picks:
        status = session.exec(select(UserCompetitionStatus).where(
            and_(UserCompetitionStatus.user_id == pick.user_id, UserCompetitionStatus.competition_id == gw.competition_id)
        )).first()
        if not status or status.status != "ACTIVE": continue
        
        fixture = next((f for f in fixtures if f.home_team == pick.team_name or f.away_team == pick.team_name), None)
        if fixture and fixture.status == 'FINISHED' and fixture.winner != pick.team_name:
            status.status = "OUT"
            status.is_active = False
            if comp and comp.code == "WC":
                if fixture.stage in ['GROUP_STAGE', 'ROUND_OF_32', 'ROUND_OF_16', 'QUARTER_FINALS']:
                    status.eligible_for_rebuy = True
            session.add(status)
    
    active_statuses = session.exec(select(UserCompetitionStatus).where(
        and_(UserCompetitionStatus.competition_id == gw.competition_id, UserCompetitionStatus.status == "ACTIVE")
    )).all()
    
    for s in active_statuses:
        user = session.get(User, s.user_id)
        if user.is_admin: continue
        user_pick = session.exec(select(Pick).where(and_(Pick.user_id == s.user_id, Pick.gameweek_id == gw.id))).first()
        if not user_pick:
            s.status = "OUT"
            s.is_active = False
            if comp and comp.code == "WC":
                 if fixtures and fixtures[0].stage in ['GROUP_STAGE', 'ROUND_OF_32', 'ROUND_OF_16', 'QUARTER_FINALS']:
                     s.eligible_for_rebuy = True
            session.add(s)
    
    gw.is_processed = True
    session.add(gw)

    next_gw = session.exec(select(Gameweek).where(
        and_(Gameweek.competition_id == gw.competition_id, Gameweek.number == gw.number + 1)
    )).first()
    
    if next_gw:
        gw.is_current = False
        next_gw.is_current = True
        session.add(next_gw)

    session.commit()
    return {"message": f"Gameweek {gw.number} processed successfully."}

@app.get("/admin/competitions")
async def get_competitions(admin: User = Depends(get_admin_user), session: Session = Depends(get_session)):
    return session.exec(select(Competition)).all()

@app.get("/admin/gameweeks")
async def get_gameweeks(competition_id: int = 2, admin: User = Depends(get_admin_user), session: Session = Depends(get_session)):
    return session.exec(select(Gameweek).where(Gameweek.competition_id == competition_id).order_by(Gameweek.number)).all()

# --- Player Routes ---

@app.get("/fixtures")
async def get_current_fixtures(competition_id: int = 2, session: Session = Depends(get_session)):
    current_gw = session.exec(select(Gameweek).where(
        and_(Gameweek.competition_id == competition_id, Gameweek.is_current == True)
    )).first()
    if not current_gw: return []
    fixtures = session.exec(select(Fixture).where(Fixture.gameweek_id == current_gw.id).order_by(Fixture.kickoff_time)).all()
    return [{
        "id": f.id,
        "home_team": f.home_team,
        "away_team": f.away_team,
        "home_team_crest": f.home_team_crest,
        "away_team_crest": f.away_team_crest,
        "kickoff_time": f.kickoff_time,
        "status": f.status,
        "stage": f.stage,
        "gameweek": { "id": current_gw.id, "number": current_gw.number, "deadline": current_gw.deadline }
    } for f in fixtures]

@app.post("/picks")
async def make_pick(team_name: str, competition_id: int = 2, current_user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    status = session.exec(select(UserCompetitionStatus).where(
        and_(UserCompetitionStatus.user_id == current_user.id, UserCompetitionStatus.competition_id == competition_id)
    )).first()
    
    if not status or status.status == "PENDING":
        raise HTTPException(status_code=400, detail="You are pending approval for this competition")
    
    if status.status == "OUT":
        raise HTTPException(status_code=400, detail="You are eliminated from this competition")
    
    current_gw = session.exec(select(Gameweek).where(
        and_(Gameweek.competition_id == competition_id, Gameweek.is_current == True)
    )).first()
    
    if not current_gw: raise HTTPException(status_code=400, detail="No active stage")
    if datetime.now(timezone.utc).replace(tzinfo=None) > current_gw.deadline:
        raise HTTPException(status_code=400, detail="Deadline passed")
    
    comp = session.get(Competition, competition_id)
    sample_fix = session.exec(select(Fixture).where(Fixture.gameweek_id == current_gw.id)).first()
    is_knockout = sample_fix and sample_fix.stage not in ['REGULAR', 'GROUP_STAGE']

    # Determine rollover context: only check picks after the most recent rollover
    latest_rollover = session.exec(select(Gameweek).where(
        and_(Gameweek.competition_id == competition_id, Gameweek.is_rollover == True)
    ).order_by(desc(Gameweek.id))).first()
    rollover_threshold_id = latest_rollover.id if latest_rollover else 0

    if not is_knockout or (comp and comp.type == 'LEAGUE'):
        prev_pick = session.exec(select(Pick).where(and_(
            Pick.user_id == current_user.id,
            Pick.competition_id == competition_id,
            Pick.team_name == team_name,
            Pick.gameweek_id != current_gw.id,
            Pick.gameweek_id >= rollover_threshold_id
        ))).first()
        
        if prev_pick:
            if comp and comp.code == "WC":
                prev_fix = session.exec(select(Fixture).where(and_(
                    Fixture.gameweek_id == prev_pick.gameweek_id,
                    (Fixture.home_team == team_name) | (Fixture.away_team == team_name)
                ))).first()
                if prev_fix and prev_fix.stage == 'GROUP_STAGE':
                    raise HTTPException(status_code=400, detail="Team already used in Group Stage")
            else:
                raise HTTPException(status_code=400, detail="Team already used since last rollover")
    
    fixture = session.exec(select(Fixture).where(and_(
        Fixture.gameweek_id == current_gw.id,
        (Fixture.home_team == team_name) | (Fixture.away_team == team_name)
    ))).first()
    
    if not fixture: raise HTTPException(status_code=400, detail="Invalid team selection")
    if datetime.now(timezone.utc).replace(tzinfo=None) > fixture.kickoff_time:
        raise HTTPException(status_code=400, detail=f"Match for {team_name} has already started")

    existing_pick = session.exec(select(Pick).where(and_(
        Pick.user_id == current_user.id, Pick.gameweek_id == current_gw.id
    ))).first()
    
    if existing_pick:
        existing_pick.team_name = team_name
        existing_pick.timestamp = datetime.now(timezone.utc).replace(tzinfo=None)
    else:
        new_pick = Pick(user_id=current_user.id, gameweek_id=current_gw.id, competition_id=competition_id, team_name=team_name)
        session.add(new_pick)
    
    session.commit()
    return {"message": "Pick saved"}

@app.get("/admin/fixtures/{gw_id}")
async def get_admin_fixtures(gw_id: int, admin: User = Depends(get_admin_user), session: Session = Depends(get_session)):
    logger.info(f"Admin fetching fixtures for gameweek {gw_id}")
    return session.exec(select(Fixture).where(Fixture.gameweek_id == gw_id).order_by(Fixture.kickoff_time)).all()

@app.get("/public/gameweeks")
async def get_public_gameweeks(competition_id: int = 2, session: Session = Depends(get_session)):
    return session.exec(select(Gameweek).where(Gameweek.competition_id == competition_id).order_by(Gameweek.number)).all()

@app.get("/public/fixtures/{gw_id}")
async def get_public_fixtures(gw_id: int, session: Session = Depends(get_session)):
    return session.exec(select(Fixture).where(Fixture.gameweek_id == gw_id).order_by(Fixture.kickoff_time)).all()

@app.get("/public/standings")
async def get_public_standings(competition_id: int = 2, session: Session = Depends(get_session)):
    users = session.exec(select(User).where(User.is_admin == False)).all()
    current_gw = session.exec(select(Gameweek).where(
        and_(Gameweek.competition_id == competition_id, Gameweek.is_current == True)
    )).first()
    
    statuses = session.exec(select(UserCompetitionStatus).where(
        UserCompetitionStatus.competition_id == competition_id
    )).all()
    status_map = {s.user_id: s for s in statuses}
    
    total_re_entries = sum(s.number_of_re_entries for s in statuses)
    total_rollover_re_entries = sum(getattr(s, 'number_of_rollovers', 0) for s in statuses)
    paid_entries = sum(1 for s in statuses if s.paid or s.status == 'ACTIVE')
    prize_pot = (paid_entries + total_re_entries + total_rollover_re_entries) * 5
    
    results = []
    for u in users:
        status = status_map.get(u.id)
        if not status: continue
        pick = None
        pick_crest = None
        if current_gw:
            pick_obj = session.exec(select(Pick).where(and_(Pick.user_id == u.id, Pick.gameweek_id == current_gw.id))).first()
            if pick_obj: 
                pick = pick_obj.team_name
                # Find crest for this pick from the fixture list
                fix_for_pick = session.exec(select(Fixture).where(and_(
                    Fixture.gameweek_id == current_gw.id,
                    (Fixture.home_team == pick) | (Fixture.away_team == pick)
                ))).first()
                if fix_for_pick:
                    pick_crest = fix_for_pick.home_team_crest if fix_for_pick.home_team == pick else fix_for_pick.away_team_crest
        
        results.append({
            "name": u.name,
            "is_active": status.status == "ACTIVE",
            "is_pending": status.status == "PENDING",
            "eligible_for_rebuy": status.eligible_for_rebuy,
            "current_pick": pick,
            "current_pick_crest": pick_crest,
            "re_entries": status.number_of_re_entries,
            "rollover_re_entries": getattr(status, 'number_of_rollovers', 0)
        })
    
    return {
        "gw_id": current_gw.number if current_gw else None,
        "standings": results,
        "total_re_entries": total_re_entries,
        "total_rollover_re_entries": total_rollover_re_entries,
        "prize_pot": prize_pot
    }

@app.get("/history")
async def get_user_history(competition_id: int = 2, current_user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    picks = session.exec(select(Pick).where(and_(
        Pick.user_id == current_user.id, Pick.competition_id == competition_id
    )).order_by(Pick.gameweek_id)).all()
    
    history = []
    for pick in picks:
        gw = session.get(Gameweek, pick.gameweek_id)
        if not gw: continue
        fixture = session.exec(select(Fixture).where(and_(
            Fixture.gameweek_id == pick.gameweek_id,
            (Fixture.home_team == pick.team_name) | (Fixture.away_team == pick.team_name)
        ))).first()
        
        outcome = "Pending"
        if fixture:
            if fixture.status == 'FINISHED':
                outcome = "WON" if fixture.winner == pick.team_name else "LOST"
            elif fixture.status in ['POSTPONED', 'CANCELLED']:
                outcome = "THROUGH (Postponed)" if gw.is_processed else "POSTPONED"
            elif fixture.status == 'IN_PLAY': outcome = "In Play"
        
        history.append({
            "gameweek_number": gw.number,
            "team_name": pick.team_name,
            "team_crest": fixture.home_team_crest if fixture.home_team == pick.team_name else fixture.away_team_crest if fixture else None,
            "outcome": outcome,
            "is_processed": gw.is_processed
        })
    return history

@app.get("/public/competitions")
async def get_public_competitions(session: Session = Depends(get_session)):
    return session.exec(select(Competition).where(Competition.is_active == True)).all()

app.mount("/", StaticFiles(directory="frontend", html=True), name="frontend")
