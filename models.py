from datetime import datetime, timezone
from typing import List, Optional
from sqlmodel import Field, Relationship, SQLModel

class Competition(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    code: str = Field(index=True)  # e.g., 'PL', 'WC'
    is_active: bool = Field(default=True)
    type: str = Field(default="LEAGUE") # LEAGUE or TOURNAMENT

    gameweeks: List["Gameweek"] = Relationship(back_populates="competition")
    user_statuses: List["UserCompetitionStatus"] = Relationship(back_populates="competition")

class UserCompetitionStatus(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id")
    competition_id: int = Field(foreign_key="competition.id")
    status: str = Field(default="PENDING") # PENDING, ACTIVE, OUT
    is_active: bool = Field(default=True) # Kept for DB compatibility, but logic uses .status
    eligible_for_rebuy: bool = Field(default=False)
    number_of_re_entries: int = Field(default=0)
    number_of_rollovers: int = Field(default=0)
    paid: bool = Field(default=False)

    user: "User" = Relationship(back_populates="competition_statuses")
    competition: Competition = Relationship(back_populates="user_statuses")

class User(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    pin: Optional[str] = Field(default=None, index=True)  # 5 digit PIN
    is_active: bool = Field(default=True) # Site-wide active status
    is_admin: bool = Field(default=False)
    
    picks: List["Pick"] = Relationship(back_populates="user")
    competition_statuses: List["UserCompetitionStatus"] = Relationship(back_populates="user")

class Gameweek(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    number: int  # The matchday number or stage sequence
    competition_id: int = Field(foreign_key="competition.id", default=2)
    deadline: datetime
    is_current: bool = Field(default=False)
    is_processed: bool = Field(default=False)
    re_entry_allowed: bool = Field(default=False)
    is_rollover: bool = Field(default=False)

    competition: Competition = Relationship(back_populates="gameweeks")
    fixtures: List["Fixture"] = Relationship(back_populates="gameweek")
    picks: List["Pick"] = Relationship(back_populates="gameweek")

class Fixture(SQLModel, table=True):
    id: int = Field(primary_key=True)  # External API ID
    gameweek_id: int = Field(foreign_key="gameweek.id")
    competition_id: int = Field(foreign_key="competition.id", default=2)
    home_team: Optional[str] = None
    away_team: Optional[str] = None
    home_team_crest: Optional[str] = None
    away_team_crest: Optional[str] = None
    kickoff_time: datetime
    status: str  # SCHEDULED, TIMED, IN_PLAY, FINISHED, POSTPONED
    stage: str = Field(default="REGULAR") # MD1, MD2, MD3, R32, R16, QF, SF, FINAL
    home_score: Optional[int] = None
    away_score: Optional[int] = None
    winner: Optional[str] = None  # Team name or 'DRAW'

    gameweek: Gameweek = Relationship(back_populates="fixtures")

class Pick(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id")
    gameweek_id: int = Field(foreign_key="gameweek.id")
    competition_id: int = Field(foreign_key="competition.id", default=2)
    team_name: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc).replace(tzinfo=None))

    user: User = Relationship(back_populates="picks")
    gameweek: Gameweek = Relationship(back_populates="picks")
