import sqlite3
import os

DB_PATH = "lms.db"
BACKUP_PATH = "lms.db.backup_before_fee"

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

        # 2. Add entry_fee column to competition if it doesn't exist
        cursor.execute("PRAGMA table_info(competition)")
        columns = [row[1] for row in cursor.fetchall()]
        
        if "entry_fee" not in columns:
            print("Adding entry_fee column to competition table...")
            cursor.execute("ALTER TABLE competition ADD COLUMN entry_fee FLOAT DEFAULT 5.0")
        
        # 3. Update Premier League 26/27 fee to 7.5
        print("Updating Premier League 26/27 entry fee to 7.5...")
        cursor.execute("UPDATE competition SET entry_fee = 7.5 WHERE name LIKE '%Premier League 26/27%' OR code = 'PL' AND is_active = 1")

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
