from fastapi import FastAPI, Query, HTTPException, Path
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import os
import psycopg2
from psycopg2.extras import RealDictCursor
from typing import Optional
from datetime import datetime

app = FastAPI(title="Total Battle Dashboard API")

# Enable CORS for local dev
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Database Connection Settings
DB_HOST = "localhost"
DB_NAME = "tb_automation"
DB_USER = "tb_user"
DB_PASS = "tb_pass"
DB_PORT = "5432"

def get_db():
    return psycopg2.connect(
        host=DB_HOST,
        database=DB_NAME,
        user=DB_USER,
        password=DB_PASS,
        port=DB_PORT
    )

# Pydantic models for request bodies
class PlayerCreate(BaseModel):
    username: str

class PlayerUpdate(BaseModel):
    username: str

class SettingsUpdate(BaseModel):
    weekly_goal: int

class FeedbackCreate(BaseModel):
    username: str
    content: str

# --- API ENDPOINTS ---

@app.get("/api/leaderboard")
def get_leaderboard(
    search: Optional[str] = None,
    sort_by: Optional[str] = "total_score",
    order: Optional[str] = "desc"
):
    """Returns the aggregated stats for players, with filtering and sorting."""
    conn = get_db()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            # We will use the CTE dynamic points view logic, but we can't easily filter by date 
            # if we use the pre-grouped VIEW. Let's write a custom query that aggregates on the fly
            # so we can apply date filters in the future if needed.
            
            # Since the user wants to see the overall stats (or current week), we aggregate everything.
            # (Date filtering can be added to the WHERE clause of `chest_logs c`)
            
            query = """
                WITH calculated_logs AS (
                    SELECT 
                        player_id,
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
                    p.id,
                    p.username,
                    COUNT(*) FILTER (WHERE c.chest_type = 'common') AS common_chests,
                    COUNT(*) FILTER (WHERE c.chest_type = 'rare') AS rare_chests,
                    COUNT(*) FILTER (WHERE c.chest_type = 'epic') AS epic_chests,
                    COUNT(*) FILTER (WHERE c.chest_type = 'event') AS event_chests,
                    COALESCE(SUM(c.dynamic_points), 0) AS total_score
                FROM players p
                LEFT JOIN calculated_logs c ON p.id = c.player_id
            """
            
            params = []
            if search:
                query += " WHERE p.username ILIKE %s"
                params.append(f"%{search}%")
                
            query += " GROUP BY p.id, p.username"
            
            # Safe sorting
            valid_sort_cols = ["username", "common_chests", "rare_chests", "epic_chests", "event_chests", "total_score"]
            if sort_by not in valid_sort_cols:
                sort_by = "total_score"
            sort_order = "ASC" if order.lower() == "asc" else "DESC"
            
            query += f" ORDER BY {sort_by} {sort_order} NULLS LAST"
            
            cursor.execute(query, params)
            stats = cursor.fetchall()
            return {"status": "success", "data": stats}
    except Exception as e:
        return {"status": "error", "message": str(e)}
    finally:
        conn.close()


@app.get("/api/players")
def get_players():
    """List all players."""
    conn = get_db()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute("SELECT id, username FROM players ORDER BY username ASC")
            players = cursor.fetchall()
            return {"status": "success", "data": players}
    except Exception as e:
        return {"status": "error", "message": str(e)}
    finally:
        conn.close()


@app.post("/api/players")
def create_player(player: PlayerCreate):
    """Create a new player."""
    conn = get_db()
    try:
        with conn.cursor() as cursor:
            cursor.execute("INSERT INTO players (username) VALUES (%s) RETURNING id", (player.username,))
            new_id = cursor.fetchone()[0]
        conn.commit()
        return {"status": "success", "message": "Player created", "id": new_id}
    except Exception as e:
        conn.rollback()
        return {"status": "error", "message": str(e)}
    finally:
        conn.close()


@app.put("/api/players/{player_id}")
def update_player(player_id: int, player: PlayerUpdate):
    """Rename a player."""
    conn = get_db()
    try:
        with conn.cursor() as cursor:
            cursor.execute("UPDATE players SET username = %s WHERE id = %s", (player.username, player_id))
            if cursor.rowcount == 0:
                raise HTTPException(status_code=404, detail="Player not found")
        conn.commit()
        return {"status": "success", "message": "Player updated"}
    except HTTPException:
        raise
    except Exception as e:
        conn.rollback()
        return {"status": "error", "message": str(e)}
    finally:
        conn.close()


@app.delete("/api/players/{player_id}")
def delete_player(player_id: int):
    """Delete a player. Cascades to their chests."""
    conn = get_db()
    try:
        with conn.cursor() as cursor:
            cursor.execute("DELETE FROM players WHERE id = %s", (player_id,))
            if cursor.rowcount == 0:
                raise HTTPException(status_code=404, detail="Player not found")
        conn.commit()
        return {"status": "success", "message": "Player deleted"}
    except HTTPException:
        raise
    except Exception as e:
        conn.rollback()
        return {"status": "error", "message": str(e)}
    finally:
        conn.close()


@app.get("/api/players/{player_id}/chests")
def get_player_chests(player_id: int):
    """List all chests for a specific player."""
    conn = get_db()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            # We dynamically calculate points for each chest here too
            query = """
                SELECT 
                    id,
                    chest_title,
                    chest_type,
                    chest_level,
                    source,
                    acquired_at,
                    CASE 
                        WHEN chest_type = 'common' THEN 
                            CASE chest_level WHEN 5 THEN 0 WHEN 10 THEN 1 WHEN 15 THEN 5 WHEN 20 THEN 15 WHEN 25 THEN 30 WHEN 30 THEN 60 ELSE 0 END
                        WHEN chest_type = 'rare' THEN
                            CASE chest_level WHEN 10 THEN 1 WHEN 15 THEN 5 WHEN 20 THEN 20 WHEN 25 THEN 35 WHEN 30 THEN 65 ELSE 0 END
                        WHEN chest_type IN ('epic', 'event') THEN
                            CASE chest_level WHEN 5 THEN 0 WHEN 10 THEN 5 WHEN 15 THEN 10 WHEN 20 THEN 25 WHEN 25 THEN 50 WHEN 30 THEN 80 WHEN 35 THEN 140 ELSE 0 END
                        ELSE 0
                    END as points
                FROM chest_logs
                WHERE player_id = %s
                ORDER BY acquired_at DESC NULLS LAST
            """
            cursor.execute(query, (player_id,))
            chests = cursor.fetchall()
            
            # Fetch player name
            cursor.execute("SELECT username FROM players WHERE id = %s", (player_id,))
            player_row = cursor.fetchone()
            username = player_row['username'] if player_row else "Unknown"
            
            return {"status": "success", "data": {"username": username, "chests": chests}}
    except Exception as e:
        return {"status": "error", "message": str(e)}
    finally:
        conn.close()


@app.get("/api/settings")
def get_settings():
    """Retrieve application settings."""
    conn = get_db()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute("SELECT key, value FROM settings")
            rows = cursor.fetchall()
            settings = {row['key']: row['value'] for row in rows}
            return {"status": "success", "data": settings}
    except Exception as e:
        return {"status": "error", "message": str(e)}
    finally:
        conn.close()


@app.post("/api/settings")
def update_settings(settings: SettingsUpdate):
    """Update weekly goal setting."""
    if not (0 <= settings.weekly_goal <= 90000):
        raise HTTPException(status_code=400, detail="Weekly goal must be between 0 and 90,000")
        
    conn = get_db()
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                INSERT INTO settings (key, value) VALUES ('weekly_goal', %s)
                ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value
            """, (str(settings.weekly_goal),))
        conn.commit()
        return {"status": "success", "message": "Settings updated"}
    except Exception as e:
        conn.rollback()
        return {"status": "error", "message": str(e)}
    finally:
        conn.close()


@app.post("/api/feedback")
def submit_feedback(fb: FeedbackCreate):
    """Submit new feedback."""
    conn = get_db()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                "INSERT INTO feedback (username, content) VALUES (%s, %s)",
                (fb.username, fb.content)
            )
        conn.commit()
        return {"status": "success", "message": "Feedback submitted"}
    except Exception as e:
        conn.rollback()
        return {"status": "error", "message": str(e)}
    finally:
        conn.close()


@app.get("/api/feedback")
def get_feedback():
    """Retrieve all feedback entries."""
    conn = get_db()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute("SELECT * FROM feedback ORDER BY created_at DESC")
            feedback_entries = cursor.fetchall()
            return {"status": "success", "data": feedback_entries}
    except Exception as e:
        return {"status": "error", "message": str(e)}
    finally:
        conn.close()


# --- FRONTEND MOUNTING ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DASHBOARD_DIR = os.path.join(BASE_DIR, "dashboard")
if not os.path.exists(DASHBOARD_DIR):
    os.makedirs(DASHBOARD_DIR)

app.mount("/assets", StaticFiles(directory=DASHBOARD_DIR), name="assets")

@app.get("/")
def serve_dashboard():
    return FileResponse(os.path.join(DASHBOARD_DIR, "index.html"))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)
