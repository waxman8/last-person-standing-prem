import asyncio
import logging
import sys
from datetime import datetime, timedelta, timezone
from sqlmodel import select, and_, col
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
                now = datetime.now(timezone.utc)
                
                # Rule B: Check if any match is currently "on"
                # "On" means it has started and it's not finished/postponed/cancelled
                match_on = session.exec(
                    select(Fixture).where(
                        Fixture.kickoff_time <= now,
                        col(Fixture.status).not_in(["FINISHED", "POSTPONED", "CANCELLED"])
                    )
                ).first() is not None

                if match_on:
                    # Rule B: poll every 5 mins while a match is on
                    next_run_seconds = 300
                    logger.info(f"{get_ts()} - scheduler - Match(es) currently in play or pending completion. Next poll in 5 mins.")
                else:
                    # Rule A: no match on, sleep until 5 mins after the start of the next match
                    next_fixture = session.exec(
                        select(Fixture)
                        .where(Fixture.kickoff_time > now)
                        .order_by(Fixture.kickoff_time)
                    ).first()
                    
                    if next_fixture:
                        # Sleep until 5 mins after the next kickoff
                        target_time = next_fixture.kickoff_time + timedelta(minutes=5)
                        next_run_seconds = (target_time - now).total_seconds()
                        
                        # Ensure we don't sleep for a negative amount or too soon
                        if next_run_seconds < 60:
                            next_run_seconds = 300 # Check again in 5 minutes
                            logger.info(f"{get_ts()} - scheduler - Next fixture is very soon or just started. Checking again in 5 mins.")
                        else:
                            logger.info(f"{get_ts()} - scheduler - No matches in play. Next match starts at {next_fixture.kickoff_time}. Next run in {round(next_run_seconds/60)} mins (5 mins after kickoff).")
                    else:
                        # No more fixtures at all (end of season?)
                        next_run_seconds = 86400 # 24 hours
                        logger.info(f"{get_ts()} - scheduler - No future fixtures found. Sleeping for 24 hours.")
                
                logger.info(f"{get_ts()} - scheduler - Worker sleeping for {round(next_run_seconds)} seconds")
                await asyncio.sleep(next_run_seconds)

        except Exception as e:
            logger.error(f"{get_ts()} - scheduler - Error in scheduler worker: {e}", exc_info=True)
            await asyncio.sleep(300) # Sleep 5 mins on error before retrying
