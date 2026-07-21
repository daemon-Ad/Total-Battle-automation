import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime
import difflib
import os
import hashlib
from dotenv import load_dotenv

load_dotenv()

# Database Connection Settings from Environment Variables
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_NAME = os.getenv("DB_NAME", "tb_automation")
DB_USER = os.getenv("DB_USER", "tb_user")
DB_PASS = os.getenv("DB_PASS", "tb_pass")
DB_PORT = os.getenv("DB_PORT", "5432")

def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()

def get_connection():
    """Establish and return a database connection."""
    return psycopg2.connect(
        host=DB_HOST,
        database=DB_NAME,
        user=DB_USER,
        password=DB_PASS,
        port=DB_PORT
    )

def setup_schema():
    """Create the necessary tables if they don't exist."""
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            # Create players table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS players (
                    id SERIAL PRIMARY KEY,
                    username TEXT UNIQUE NOT NULL,
                    rank TEXT DEFAULT 'Officer',
                    is_active BOOLEAN DEFAULT TRUE,
                    guardsman_level INT DEFAULT 0,
                    specialist_level INT DEFAULT 0,
                    monster_level INT DEFAULT 0
                )
            """)
            
            # Migrate existing tables
            cursor.execute("""
                ALTER TABLE players ADD COLUMN IF NOT EXISTS rank TEXT DEFAULT 'Officer';
                ALTER TABLE players ADD COLUMN IF NOT EXISTS is_active BOOLEAN DEFAULT TRUE;
                ALTER TABLE players ADD COLUMN IF NOT EXISTS guardsman_level INT DEFAULT 0;
                ALTER TABLE players ADD COLUMN IF NOT EXISTS specialist_level INT DEFAULT 0;
                ALTER TABLE players ADD COLUMN IF NOT EXISTS monster_level INT DEFAULT 0;
            """)

            # Create users table for dashboard authentication
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id SERIAL PRIMARY KEY,
                    username TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL
                )
            """)
            
            # Seed default users if they don't exist
            default_users = [
                ("Shanks", hash_password("shanks123")),
                ("Overlord", hash_password("overlord123")),
                ("Serena", hash_password("serena123"))
            ]
            for user, phash in default_users:
                cursor.execute(
                    "INSERT INTO users (username, password_hash) VALUES (%s, %s) ON CONFLICT (username) DO NOTHING",
                    (user, phash)
                )
            
            # Create settings table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )
            """)
            
            # Default weekly goal
            cursor.execute("INSERT INTO settings (key, value) VALUES ('weekly_goal', '700') ON CONFLICT DO NOTHING")
            
            # Create feedback table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS feedback (
                    id SERIAL PRIMARY KEY,
                    username TEXT NOT NULL,
                    content TEXT NOT NULL,
                    created_at TIMESTAMPTZ DEFAULT NOW()
                )
            """)
            
            # Create chest_logs table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS chest_logs (
                    id SERIAL PRIMARY KEY,
                    player_id INT REFERENCES players(id) ON DELETE CASCADE,
                    chest_title TEXT NOT NULL,
                    chest_type TEXT,
                    chest_level INT NOT NULL,
                    source TEXT,
                    timer_text TEXT,
                    claimed_at TIMESTAMPTZ DEFAULT NOW(),
                    acquired_at TIMESTAMPTZ,
                    points INT DEFAULT 0
                )
            """)
            
            # Apply schema updates to existing tables just in case they were already created
            try:
                cursor.execute("ALTER TABLE chest_logs ADD COLUMN IF NOT EXISTS acquired_at TIMESTAMPTZ;")
                cursor.execute("ALTER TABLE chest_logs ADD COLUMN IF NOT EXISTS points INT DEFAULT 0;")
                cursor.execute("""
                    ALTER TABLE chest_logs DROP CONSTRAINT IF EXISTS chest_logs_player_id_fkey;
                    ALTER TABLE chest_logs ADD CONSTRAINT chest_logs_player_id_fkey 
                    FOREIGN KEY (player_id) REFERENCES players(id) ON DELETE CASCADE;
                """)
            except psycopg2.Error as e:
                # Ignore if they somehow error out (e.g., table not fully initialized)
                print(f"Warning on alter tables: {e}")
                pass

            # Create the dynamic view for weekly stats
            cursor.execute("""
                CREATE OR REPLACE VIEW weekly_player_stats AS
                WITH calculated_logs AS (
                    SELECT 
                        player_id,
                        acquired_at,
                        chest_type,
                        CASE 
                            WHEN chest_type = 'common' THEN 
                                CASE chest_level WHEN 5 THEN 0 WHEN 10 THEN 1 WHEN 15 THEN 5 WHEN 20 THEN 15 WHEN 25 THEN 30 WHEN 30 THEN 60 ELSE 0 END
                            WHEN chest_type = 'rare' THEN
                                CASE chest_level WHEN 10 THEN 1 WHEN 15 THEN 5 WHEN 20 THEN 20 WHEN 25 THEN 35 WHEN 30 THEN 65 ELSE 0 END
                            WHEN chest_type IN ('epic', 'event') THEN
                                CASE chest_level WHEN 5 THEN 0 WHEN 10 THEN 5 WHEN 15 THEN 10 WHEN 20 THEN 25 WHEN 25 THEN 50 WHEN 30 THEN 80 WHEN 35 THEN 140 ELSE 0 END
                            ELSE 0
                        END as dynamic_points
                    FROM chest_logs
                )
                SELECT 
                    p.username,
                    date_trunc('week', c.acquired_at) AS week,
                    COUNT(*) FILTER (WHERE c.chest_type = 'common') AS common_chests,
                    COUNT(*) FILTER (WHERE c.chest_type = 'rare') AS rare_chests,
                    COUNT(*) FILTER (WHERE c.chest_type = 'epic') AS epic_chests,
                    COUNT(*) FILTER (WHERE c.chest_type = 'event') AS event_chests,
                    SUM(c.dynamic_points) AS total_score
                FROM calculated_logs c
                JOIN players p ON c.player_id = p.id
                GROUP BY p.username, week
            """)
        conn.commit()
        print("Schema setup successfully.")
    except Exception as e:
        conn.rollback()
        import sys
        print(f"Error setting up schema: {e}", file=sys.stderr)
    finally:
        conn.close()

def match_player(username: str) -> int:
    """Get the player ID for a username using fuzzy matching. Fallback to 98 (Unknown Player)."""
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT id, username FROM players")
            players = cursor.fetchall()
            
            # 1. Exact match
            for pid, p_name in players:
                if username == p_name:
                    return pid
                    
            # 2. Lowercase match
            for pid, p_name in players:
                if username.lower() == p_name.lower():
                    return pid
                    
            # 3. Fuzzy match
            names = [p_name for pid, p_name in players]
            matches = difflib.get_close_matches(username, names, n=1, cutoff=0.7)
            if matches:
                matched_name = matches[0]
                for pid, p_name in players:
                    if p_name == matched_name:
                        return pid
                        
            # If nothing was found, return Unknown Player (98)
            return 98
    except Exception as e:
        import sys
        print(f"Error matching player: {e}", file=sys.stderr)
        return 98
    finally:
        conn.close()

def log_chest(username: str, title: str, chest_type: str, level: int, source: str, timer_text: str, acquired_at=None, points=0):
    """Log a claimed chest into the database."""
    player_id = match_player(username)
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                INSERT INTO chest_logs (player_id, chest_title, chest_type, chest_level, source, timer_text, acquired_at, points)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """, (player_id, title, chest_type, level, source, timer_text, acquired_at, points))
        conn.commit()
        print(f"Logged chest: {title} (Level {level}) from {username} (Matched ID: {player_id})")
    except Exception as e:
        conn.rollback()
        import sys
        print(f"Error logging chest: {e}", file=sys.stderr)
    finally:
        conn.close()

if __name__ == "__main__":
    setup_schema()
