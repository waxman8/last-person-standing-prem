# Plan: Water-tight Datetime Enforcement

The goal is to eliminate `TypeError: can't compare offset-naive and offset-aware datetimes` by ensuring that every `datetime` object in the application—whether synced from an API, loaded from the database, or created in memory—is guaranteed to be timezone-aware (UTC).

## 1. Model-Level Enforcement (`models.py`)
Add Pydantic validators to the `SQLModel` classes to intercept and "fix" any naive datetimes during object instantiation.

- **Target Fields**: `Gameweek.deadline`, `Fixture.kickoff_time`, `Pick.timestamp`.
- **Logic**: If a `datetime` is naive, attach `timezone.utc`.

```python
from pydantic import validator

@validator("kickoff_time", pre=True)
def ensure_utc(cls, v):
    if isinstance(v, datetime) and v.tzinfo is None:
        return v.replace(tzinfo=timezone.utc)
    return v
```

## 2. Sync-Level Enforcement (`services.py`)
Ensure that the initial parsing of API data explicitly creates UTC-aware objects.

- **Location**: `sync_fixtures_logic` function.
- **Change**: When parsing `utcDate` from the football API, ensure the resulting `datetime` object is explicitly UTC.

## 3. Database Cleanup
Manually trigger the migration logic to "clean" the existing Quarterfinal data in `lms.db` that currently lacks the UTC offset strings. This fixes the immediate crash without needing to wait for a container restart.

- **Action**: Run the `UPDATE` statements from `database.py` via a one-off script.

## 4. Verification
Create a test script `utils/verify_fix.py` that:
1. Instantiates a `Fixture` with a naive date and asserts it becomes aware.
2. Loads a fixture from the DB and attempts the comparison currently failing in `main.py`.

## Execution Order
1. Update `models.py` (The Shield).
2. Update `services.py` (The Source).
3. Run Cleanup Script (The Data).
4. Verify.
