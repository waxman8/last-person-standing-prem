from sqlmodel import Session, select
from database import engine, init_db
from models import User

def create_admin():
    init_db()
    with Session(engine) as session:
        admin = session.exec(select(User).where(User.pin == "99999")).first()
        if not admin:
            admin = User(name="Admin", pin="99999", is_active=True, is_admin=True)
            session.add(admin)
            session.commit()
            print("Admin created with PIN: 99999")
        else:
            print("Admin already exists")

if __name__ == "__main__":
    create_admin()
