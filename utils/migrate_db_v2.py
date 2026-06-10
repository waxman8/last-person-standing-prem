import sqlite3
import os

DB_PATH = "lms.db"
BACKUP_PATH = "lms.db.backup"

def migrate():
    # 1. Backup
    if os.path.exists(DB_PATH):
        import shutil
        shutil.copy(DB_PATH, BACKUP_PATH)
        print(f"Backup created at {BACKUP_PATH}")

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    try:
        # Start transaction
        cursor.execute("BEGIN TRANSACTION;")

        # 2. Create Competition table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS competition (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name VARCHAR NOT NULL,
            code VARCHAR NOT NULL,
            is_active BOOLEAN NOT NULL DEFAULT 1,
            type VARCHAR NOT NULL DEFAULT 'LEAGUE'
        );
        """)
        
        # 3. Create UserCompetitionStatus table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS usercompetitionstatus (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            competition_id INTEGER NOT NULL,
            is_active BOOLEAN NOT NULL DEFAULT 1,
            eligible_for_rebuy BOOLEAN NOT NULL DEFAULT 0,
            number_of_re_entries INTEGER NOT NULL DEFAULT 0,
            number_of_rollovers INTEGER NOT NULL DEFAULT 0,
            paid BOOLEAN NOT NULL DEFAULT 0,
            FOREIGN KEY(user_id) REFERENCES user(id),
            FOREIGN KEY(competition_id) REFERENCES competition(id)
        );
        """)

        # 4. Insert initial competitions
        cursor.execute("SELECT id FROM competition WHERE code = 'PL'")
        if not cursor.fetchone():
            cursor.execute("INSERT INTO competition (name, code, is_active, type) VALUES ('Premier League 24/25', 'PL', 1, 'LEAGUE')")
        
        cursor.execute("SELECT id FROM competition WHERE code = 'WC'")
        if not cursor.fetchone():
            cursor.execute("INSERT INTO competition (name, code, is_active, type) VALUES ('World Cup 2026', 'WC', 1, 'TOURNAMENT')")

        # Get PL ID
        cursor.execute("SELECT id FROM competition WHERE code = 'PL' LIMIT 1")
        pl_id = cursor.fetchone()[0]

        # 5. Migrate Gameweek table (to handle ID change and Competition linking)
        # Check if we already migrated (if 'number' column exists in gameweek)
        cursor.execute("PRAGMA table_info(gameweek)")
        columns = [row[1] for row in cursor.fetchall()]
        
        if "number" not in columns:
            print("Migrating gameweek table structure...")
            cursor.execute("ALTER TABLE gameweek RENAME TO gameweek_old")
            cursor.execute(f"""
            CREATE TABLE gameweek (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                number INTEGER NOT NULL,
                competition_id INTEGER NOT NULL DEFAULT {pl_id},
                deadline DATETIME NOT NULL,
                is_current BOOLEAN NOT NULL DEFAULT 0,
                is_processed BOOLEAN NOT NULL DEFAULT 0,
                re_entry_allowed BOOLEAN NOT NULL DEFAULT 0,
                is_rollover BOOLEAN NOT NULL DEFAULT 0,
                FOREIGN KEY(competition_id) REFERENCES competition(id)
            )
            """)
            cursor.execute(f"""
            INSERT INTO gameweek (number, deadline, is_current, is_processed, re_entry_allowed, is_rollover, competition_id)
            SELECT id, deadline, is_current, is_processed, re_entry_allowed, is_rollover, {pl_id} FROM gameweek_old
            """)
            
            # 6. Update Fixture references
            # We need to add competition_id and stage first if not exists (might have been added by previous failed run)
            cursor.execute("PRAGMA table_info(fixture)")
            fix_cols = [row[1] for row in cursor.fetchall()]
            if "competition_id" not in fix_cols:
                cursor.execute(f"ALTER TABLE fixture ADD COLUMN competition_id INTEGER DEFAULT {pl_id}")
            if "stage" not in fix_cols:
                cursor.execute("ALTER TABLE fixture ADD COLUMN stage VARCHAR DEFAULT 'REGULAR'")

            # Update gameweek_id in fixture from OLD GW ID to NEW GW ID
            cursor.execute(f"""
            UPDATE fixture SET gameweek_id = (
                SELECT g.id FROM gameweek g WHERE g.number = fixture.gameweek_id AND g.competition_id = {pl_id}
            ) WHERE competition_id = {pl_id} OR competition_id IS NULL;
            """)

            # 7. Update Pick references
            cursor.execute("PRAGMA table_info(pick)")
            pick_cols = [row[1] for row in cursor.fetchall()]
            if "competition_id" not in pick_cols:
                cursor.execute(f"ALTER TABLE pick ADD COLUMN competition_id INTEGER DEFAULT {pl_id}")
            
            cursor.execute(f"""
            UPDATE pick SET gameweek_id = (
                SELECT g.id FROM gameweek g WHERE g.number = pick.gameweek_id AND g.competition_id = {pl_id}
            ) WHERE competition_id = {pl_id} OR competition_id IS NULL;
            """)

            cursor.execute("DROP TABLE gameweek_old")
        
        # 8. Migrate User status to UserCompetitionStatus
        cursor.execute(f"""
        INSERT INTO usercompetitionstatus (user_id, competition_id, is_active, paid)
        SELECT id, {pl_id}, is_active, 1 FROM user
        WHERE id NOT IN (SELECT user_id FROM usercompetitionstatus WHERE competition_id = {pl_id})
        """)

        # Add users to WC as well
        cursor.execute("SELECT id FROM competition WHERE code = 'WC' LIMIT 1")
        wc_id = cursor.fetchone()[0]
        cursor.execute(f"""
        INSERT INTO usercompetitionstatus (user_id, competition_id, is_active, paid)
        SELECT id, {wc_id}, 1, 0 FROM user
        WHERE id NOT IN (SELECT user_id FROM usercompetitionstatus WHERE competition_id = {wc_id})
        """)

        conn.commit()
        print("Migration completed successfully.")

    except Exception as e:
        conn.rollback()
        print(f"Migration failed: {e}")
        raise e
    finally:
        conn.close()

if __name__ == "__main__":
    migrate()
