from sqlmodel import create_engine, SQLModel, Session
import os

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./lms.db")

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})

# Explicit Session factory for background workers
def SessionLocal():
    return Session(engine)

def init_db():
    SQLModel.metadata.create_all(engine)

def get_session():
    with Session(engine) as session:
        yield session
