import sqlite3
import os

DB_PATH = "lms.db"

def start_new_season():
    if not os.path.exists(DB_PATH):
        print(f"Error: Database {DB_PATH} not found.")
        return

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    try:
        cursor.execute("BEGIN TRANSACTION;")

        # 1. Deactivate all existing competitions
        print("Deactivating all existing competitions...")
        cursor.execute("UPDATE competition SET is_active = 0")

        # 2. Add Premier League 26/27
        print("Adding Premier League 26/27 competition...")
        cursor.execute("""
            INSERT INTO competition (name, code, is_active, type, entry_fee)
            VALUES ('Premier League 26/27', 'PL', 1, 'LEAGUE', 7.5)
        """)
        new_comp_id = cursor.lastrowid
        print(f"New Competition ID: {new_comp_id}")

        # 3. Get all users
        cursor.execute("SELECT id, name FROM user WHERE is_admin = 0")
        users = cursor.fetchall()
        print(f"Found {len(users)} players.")

        # 4. Create PENDING status for all players for the new competition
        print("Setting all players to PENDING for the new season...")
        for user_id, name in users:
            # Check if status already exists (unlikely for new comp, but safe)
            cursor.execute("SELECT id FROM usercompetitionstatus WHERE user_id = ? AND competition_id = ?", (user_id, new_comp_id))
            if not cursor.fetchone():
                cursor.execute("""
                    INSERT INTO usercompetitionstatus (user_id, competition_id, status, is_active, paid, eligible_for_rebuy, number_of_re_entries, number_of_rollovers)
                    VALUES (?, ?, 'PENDING', 0, 0, 0, 0, 0)
                """, (user_id, new_comp_id))
        
        conn.commit()
        print("Successfully initialized Premier League 26/27 season.")

    except Exception as e:
        conn.rollback()
        print(f"Error: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    start_new_season()
