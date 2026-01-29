from datetime import datetime
from typing import List, Optional
from sqlmodel import Field, Relationship, SQLModel

class User(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    pin: str = Field(index=True)  # 5 digit PIN
    is_active: bool = Field(default=True)
    is_admin: bool = Field(default=False)
    
    picks: List["Pick"] = Relationship(back_populates="user")

class Gameweek(SQLModel, table=True):
    id: int = Field(primary_key=True)  # Using the sequence number (e.g., 1, 2, 3...)
    deadline: datetime
    is_current: bool = Field(default=False)
    is_processed: bool = Field(default=False)

    fixtures: List["Fixture"] = Relationship(back_populates="gameweek")
    picks: List["Pick"] = Relationship(back_populates="gameweek")

class Fixture(SQLModel, table=True):
    id: int = Field(primary_key=True)  # External API ID
    gameweek_id: int = Field(foreign_key="gameweek.id")
    home_team: str
    away_team: str
    kickoff_time: datetime
    status: str  # SCHEDULED, TIMED, IN_PLAY, FINISHED, POSTPONED
    home_score: Optional[int] = None
    away_score: Optional[int] = None
    winner: Optional[str] = None  # Team name or 'DRAW'

    gameweek: Gameweek = Relationship(back_populates="fixtures")

class Pick(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id")
    gameweek_id: int = Field(foreign_key="gameweek.id")
    team_name: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)

    user: User = Relationship(back_populates="picks")
    gameweek: Gameweek = Relationship(back_populates="picks")
