import asyncio
import logging
import sys
from datetime import datetime, timedelta
from sqlmodel import select, and_
from database import SessionLocal, get_session
from models import Fixture, Gameweek
from services import sync_fixtures_logic

from uvicorn.logging import DefaultFormatter

handler = logging.StreamHandler(sys.stderr)
handler.setFormatter(DefaultFormatter('%(levelname)s:     %(message)s'))
logging.root.handlers = [handler]
logging.root.setLevel(logging.INFO)
logger = logging.getLogger(__name__)

async def fixture_scheduler_worker():
    """
    Background worker that polls for updates when fixtures are on.
    Schedules itself based on fixture start/end times.
    """
    # Helper to get formatted timestamp
    def get_ts():
        return datetime.now().strftime("%d-%m-%Y %H:%M:%S")

    while True:
        try:
            with SessionLocal() as session:
                # Step 1: Run the sync
                logger.info(f"{get_ts()} - scheduler - Starting fixture sync...")
                sync_fixtures_logic(session)
                
                # Step 2: Determine next schedule
                now = datetime.utcnow()
                
                # Get current gameweek
                current_gw = session.exec(select(Gameweek).where(Gameweek.is_current == True)).first()
                if not current_gw:
                    logger.info(f"{get_ts()} - scheduler - No current gameweek found. Sleeping for 1 hour.")
                    await asyncio.sleep(3600)
                    continue
                
                # Get fixtures for current gameweek that are not finished
                active_fixtures = session.exec(
                    select(Fixture).where(
                        and_(
                            Fixture.gameweek_id == current_gw.id,
                            Fixture.status == "IN_PLAY"
                        )
                    )
                ).all()
                
                next_run_seconds = 3600 # Default sleep 1 hour
                
                if active_fixtures:
                    # (a) if there is currently a fixture on:
                    # Determine expected end time (start time + 100 mins)
                    # Guidance: Use the fixture finishing soonest
                    
                    soonest_end = None
                    for f in active_fixtures:
                        expected_end = f.kickoff_time + timedelta(minutes=100)
                        if soonest_end is None or expected_end < soonest_end:
                            soonest_end = expected_end
                    
                    time_left_seconds = (soonest_end - now).total_seconds()
                    
                    if time_left_seconds > 600: # 10 minutes
                        # (a.i) if there is more than ten minutes left, next run in 10 mins
                        logger.info(f"{get_ts()} - scheduler - Fixture(s) in play. Soonest expected end in {round(time_left_seconds/60)} mins. Next run in 10 mins.")
                        next_run_seconds = 600
                    else:
                        # (a.ii) if there is less than ten minutes left, next run at expected end
                        # Ensure we don't schedule in the past or too soon
                        next_run_seconds = max(time_left_seconds, 30)
                        logger.info(f"{get_ts()} - scheduler - Fixture(s) finishing soon. Next run in {round(next_run_seconds)} seconds (at expected end).")
                else:
                    # (b) if there is not currently a fixture on:
                    # Find the next fixture to start
                    next_fixture = session.exec(
                        select(Fixture).where(
                            and_(
                                Fixture.gameweek_id == current_gw.id,
                                Fixture.status.in_(["SCHEDULED", "TIMED"])
                            )
                        ).order_by(Fixture.kickoff_time)
                    ).first()
                    
                    if next_fixture:
                        # schedule the next run to be 10 mins after the start of the next fixture
                        target_time = next_fixture.kickoff_time + timedelta(minutes=10)
                        wait_seconds = (target_time - now).total_seconds()
                        
                        if wait_seconds > 0:
                            next_run_seconds = wait_seconds
                            logger.info(f"{get_ts()} - scheduler - No fixtures in play. Next fixture starts at {next_fixture.kickoff_time}. Next run in {round(next_run_seconds/60)} mins (10 mins after kickoff).")
                        else:
                            # If for some reason target time is in the past but status hasn't updated to IN_PLAY yet
                            next_run_seconds = 300 # Try again in 5 mins
                            logger.info(f"{get_ts()} - scheduler - Next fixture should have started. Retrying in 5 mins.")
                    else:
                        # No more fixtures in current gameweek
                        logger.info(f"{get_ts()} - scheduler - No more active or scheduled fixtures in current gameweek. Sleeping for 4 hours.")
                        next_run_seconds = 14400 # 4 hours
                
                logger.info(f"{get_ts()} - scheduler - Worker sleeping for {round(next_run_seconds)} seconds")
                await asyncio.sleep(next_run_seconds)

        except Exception as e:
            logger.error(f"{get_ts()} - scheduler - Error in scheduler worker: {e}", exc_info=True)
            await asyncio.sleep(300) # Sleep 5 mins on error before retrying
