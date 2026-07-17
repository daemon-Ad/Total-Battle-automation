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

from db import get_connection as get_db, hash_password
import base64
from fastapi import Request, Response

# Basic Authentication Middleware
@app.middleware("http")
async def basic_auth_middleware(request: Request, call_next):
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Basic "):
        return Response(status_code=401, headers={"WWW-Authenticate": 'Basic realm="Dashboard"'})
    
    try:
        decoded = base64.b64decode(auth_header[6:]).decode("utf-8")
        username, password = decoded.split(":", 1)
    except Exception:
        return Response(status_code=401, headers={"WWW-Authenticate": 'Basic realm="Dashboard"'})
    
    # Check DB
    conn = get_db()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT password_hash FROM users WHERE username = %s", (username,))
            row = cursor.fetchone()
            if not row or row[0] != hash_password(password):
                return Response(status_code=401, headers={"WWW-Authenticate": 'Basic realm="Dashboard"'})
    except Exception:
        return Response(status_code=500, content="Database Error")
    finally:
        conn.close()
        
    response = await call_next(request)
    return response

# Pydantic models for request bodies
class PlayerCreate(BaseModel):
    username: str
    rank: str = "Officer"

class PlayerUpdate(BaseModel):
    username: str
    rank: str = "Officer"

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
            cursor.execute("""
                SELECT id, username, rank FROM players 
                ORDER BY 
                    CASE rank
                        WHEN 'Leader' THEN 1
                        WHEN 'Superior' THEN 2
                        WHEN 'Officer' THEN 3
                        WHEN 'Veteran' THEN 4
                        WHEN 'Soldier' THEN 5
                        WHEN 'Unknown' THEN 6
                        ELSE 7
                    END ASC,
                    username ASC
            """)
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
            cursor.execute("INSERT INTO players (username, rank) VALUES (%s, %s) RETURNING id", (player.username, player.rank))
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
            cursor.execute("UPDATE players SET username = %s, rank = %s WHERE id = %s", (player.username, player.rank, player_id))
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


@app.get("/api/analytics")
def get_analytics():
    """Retrieve all data needed for the advanced analytics dashboard."""
    conn = get_db()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            # 1. Get weekly goal
            cursor.execute("SELECT value FROM settings WHERE key = 'weekly_goal'")
            setting_row = cursor.fetchone()
            weekly_goal = int(setting_row['value']) if setting_row else 700
            
            # 2. Get Targets & Summary (Current Week)
            query_stats = """
                WITH calculated_logs AS (
                    SELECT 
                        player_id,
                        acquired_at,
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
                    WHERE acquired_at >= date_trunc('week', CURRENT_DATE)
                )
                SELECT 
                    p.username,
                    COALESCE(SUM(c.dynamic_points), 0) AS total_score,
                    COUNT(c.player_id) as chests
                FROM players p
                LEFT JOIN calculated_logs c ON p.id = c.player_id
                GROUP BY p.username
                ORDER BY total_score DESC
            """
            cursor.execute(query_stats)
            player_stats = cursor.fetchall()
            
            total_score = sum(p['total_score'] for p in player_stats)
            total_chests = sum(p['chests'] for p in player_stats)
            active_players = len(player_stats)
            total_goal = weekly_goal * active_players if active_players > 0 else weekly_goal
            
            on_track_players = []
            needs_attention_players = []
            
            for p in player_stats:
                score = p['total_score']
                diff = score - weekly_goal
                player_data = {
                    "username": p['username'],
                    "score": score,
                    "goal": weekly_goal,
                    "diff": diff
                }
                if score >= weekly_goal:
                    on_track_players.append(player_data)
                else:
                    needs_attention_players.append(player_data)
            
            # 3. Get Trends (Hourly for today)
            query_hourly = """
                WITH calculated_logs AS (
                    SELECT 
                        acquired_at,
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
                    WHERE acquired_at >= CURRENT_DATE
                )
                SELECT 
                    TO_CHAR(date_trunc('hour', acquired_at), 'HH24:MI') as time_label,
                    COUNT(*) as chests,
                    SUM(dynamic_points) as score
                FROM calculated_logs
                GROUP BY date_trunc('hour', acquired_at)
                ORDER BY date_trunc('hour', acquired_at)
            """
            cursor.execute(query_hourly)
            hourly_trends = cursor.fetchall()
            
            # 4. Get Trends (Daily for last 7 days)
            query_daily = """
                WITH calculated_logs AS (
                    SELECT 
                        acquired_at,
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
                    WHERE acquired_at >= (CURRENT_DATE - INTERVAL '7 days')
                )
                SELECT 
                    TO_CHAR(date_trunc('day', acquired_at), 'MM-DD') as time_label,
                    COUNT(*) as chests,
                    SUM(dynamic_points) as score
                FROM calculated_logs
                GROUP BY date_trunc('day', acquired_at)
                ORDER BY date_trunc('day', acquired_at)
            """
            cursor.execute(query_daily)
            daily_trends = cursor.fetchall()
            
            # 5. Get Sources (All time, or current week)
            query_sources = """
                SELECT 
                    CASE 
                        WHEN source ILIKE '%crypt%' THEN 'Crypts'
                        WHEN source ILIKE '%citadel%' THEN 'Citadels'
                        WHEN source ILIKE '%monster%' THEN 'Monsters'
                        WHEN source ILIKE '%event%' OR source ILIKE '%triumphal%' THEN 'Events'
                        WHEN source ILIKE '%clan wealth%' THEN 'Clan'
                        WHEN source ILIKE '%arena%' THEN 'Arena'
                        ELSE 'Resources'
                    END as category,
                    COUNT(*) as count
                FROM chest_logs
                WHERE acquired_at >= date_trunc('week', CURRENT_DATE)
                GROUP BY category
                ORDER BY count DESC
            """
            cursor.execute(query_sources)
            sources = cursor.fetchall()

            return {
                "status": "success", 
                "data": {
                    "targets": {
                        "total_score": total_score,
                        "total_chests": total_chests,
                        "total_goal": total_goal
                    },
                    "summary": {
                        "total_members": active_players,
                        "on_track_count": len(on_track_players),
                        "needs_attention_count": len(needs_attention_players),
                        "on_track_players": on_track_players,
                        "needs_attention_players": needs_attention_players
                    },
                    "trends": {
                        "hourly": hourly_trends,
                        "daily": daily_trends
                    },
                    "sources": sources
                }
            }
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
