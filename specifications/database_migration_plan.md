# Database Migration Plan

## Problem
The current `init_db` function uses `SQLModel.metadata.create_all(engine)`, which only creates tables if they don't exist. It does **not** handle adding new columns to existing tables (e.g., `is_rollover` to `Gameweek` or `number_of_rollover_re_entries` to `User`), leading to errors like `no such column`.

## Proposed Solution: Alembic
The standard, robust alternative for migrations in the SQLAlchemy/SQLModel ecosystem is **Alembic**. It works like Flyway but is tailored for Python.

### 1. Why Alembic?
- **Versioned Migrations**: Tracks which migrations have been applied using a `alembic_version` table.
- **Autogeneration**: Can detect changes in `models.py` and generate migration scripts automatically.
- **Rollback Support**: Easy to revert changes if something goes wrong.
- **Industry Standard**: Widely used in FastAPI/Flask/Django projects.

### 2. Implementation Steps

#### A. Setup
1. Install Alembic: `pip install alembic`
2. Initialize: `alembic init alembic`
3. Configure `alembic.ini` to point to `lms.db`.
4. Configure `alembic/env.py` to import our `SQLModel` metadata and `models.py`.

#### B. Generate Migration
1. Run: `alembic revision --autogenerate -m "add rollover fields"`
   - This will create a script in `alembic/versions/` adding `is_rollover` to `gameweek` and `number_of_rollover_re_entries` to `user`.

#### C. Automated Execution
Update `main.py` to run migrations on startup:
```python
from alembic.config import Config
from alembic import command

def run_migrations():
    alembic_cfg = Config("alembic.ini")
    command.upgrade(alembic_cfg, "head")

@app.on_event("startup")
async def on_startup():
    run_migrations() # Run migrations before anything else
    init_db()
    ...
```

## Alternative: "Lightweight" Migration Script
If we want to avoid the complexity of full Alembic setup for this small project, we can use a **dedicated migration script** (as proposed previously) but make it more formal by tracking versions.

## Recommendation
**Alembic** is the professional choice and will serve the project better as it grows.

## Next Steps
1. User chooses between **Alembic** or the **Lightweight Script**.
2. Implement chosen solution.
