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
    guardsman_level: int = 0
    specialist_level: int = 0
    monster_level: int = 0

class PlayerUpdate(BaseModel):
    username: str
    rank: str = "Officer"
    guardsman_level: int = 0
    specialist_level: int = 0
    monster_level: int = 0

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
    order: Optional[str] = "desc",
    timeframe: Optional[str] = "weekly",
    offset: Optional[int] = 0
):
    """Returns the aggregated stats for players, with filtering and sorting."""
    conn = get_db()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            # Determine date filters based on timeframe and offset
            from datetime import timedelta, date, datetime
            import calendar
            
            today = date.today()
            date_filter = ""
            params = []
            
            if timeframe == "daily":
                target = today - timedelta(days=offset)
                date_filter = "WHERE c.acquired_at >= %s AND c.acquired_at < %s"
                params.extend([target, target + timedelta(days=1)])
            elif timeframe == "weekly":
                start_of_week = today - timedelta(days=today.weekday())
                target_start = start_of_week - timedelta(weeks=offset)
                date_filter = "WHERE c.acquired_at >= %s AND c.acquired_at < %s"
                params.extend([target_start, target_start + timedelta(days=7)])
            elif timeframe == "monthly":
                # Rough approximation: month-1 is hard to do perfectly with just offset, but we can do ~30 days
                # Or exact month:
                target_month = today.month - offset
                target_year = today.year
                while target_month <= 0:
                    target_month += 12
                    target_year -= 1
                _, last_day = calendar.monthrange(target_year, target_month)
                start_date = date(target_year, target_month, 1)
                end_date = date(target_year, target_month, last_day) + timedelta(days=1)
                date_filter = "WHERE c.acquired_at >= %s AND c.acquired_at < %s"
                params.extend([start_date, end_date])
            elif timeframe == "overall":
                pass # no filter

            query = f"""
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
                    FROM chest_logs c
                    {date_filter}
                )
                SELECT 
                    p.id,
                    p.username,
                    COUNT(*) FILTER (WHERE c.chest_type = 'common') AS common_chests,
                    COUNT(*) FILTER (WHERE c.chest_type = 'rare') AS rare_chests,
                    COUNT(*) FILTER (WHERE c.chest_type = 'epic') AS epic_chests,
                    COUNT(*) FILTER (WHERE c.chest_type = 'event') AS event_chests,
                    COALESCE(SUM(c.dynamic_points), 0) AS total_score,
                    COALESCE(SUM(c.dynamic_points) FILTER (WHERE c.chest_type IN ('common', 'rare', 'epic')), 0) AS pure_crypt_points
                FROM players p
                LEFT JOIN calculated_logs c ON p.id = c.player_id
            """
            
            if search:
                query += " WHERE p.username ILIKE %s AND p.username NOT IN ('Unknown Player', 'Clan') AND p.is_active = TRUE"
                params.append(f"%{search}%")
            else:
                query += " WHERE p.username NOT IN ('Unknown Player', 'Clan') AND p.is_active = TRUE"
                
            query += " GROUP BY p.id, p.username"
            
            valid_sort_cols = ["username", "common_chests", "rare_chests", "epic_chests", "event_chests", "total_score", "pure_crypt_points"]
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
                SELECT id, username, rank, is_active, guardsman_level, specialist_level, monster_level FROM players 
                WHERE username NOT IN ('Unknown Player', 'Clan')
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
            # Upsert logic to handle soft-deleted players
            cursor.execute("""
                INSERT INTO players (username, rank, is_active, guardsman_level, specialist_level, monster_level) 
                VALUES (%s, %s, TRUE, %s, %s, %s)
                ON CONFLICT (username) DO UPDATE 
                SET rank = EXCLUDED.rank, 
                    is_active = TRUE,
                    guardsman_level = EXCLUDED.guardsman_level,
                    specialist_level = EXCLUDED.specialist_level,
                    monster_level = EXCLUDED.monster_level
                RETURNING id
            """, (player.username, player.rank, player.guardsman_level, player.specialist_level, player.monster_level))
            new_id = cursor.fetchone()[0]
            
            # Keep the sequence in sync just in case
            cursor.execute("SELECT setval('players_id_seq', (SELECT MAX(id) FROM players))")
            
        conn.commit()
        return {"status": "success", "message": "Player created/reactivated", "id": new_id}
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
            cursor.execute("""
                UPDATE players SET username = %s, rank = %s, guardsman_level = %s, specialist_level = %s, monster_level = %s 
                WHERE id = %s
            """, (player.username, player.rank, player.guardsman_level, player.specialist_level, player.monster_level, player_id))
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



@app.post("/api/players/{player_id}/reactivate")
def reactivate_player(player_id: int):
    """Reactivate a soft-deleted player."""
    conn = get_db()
    try:
        with conn.cursor() as cursor:
            cursor.execute("UPDATE players SET is_active = TRUE WHERE id = %s", (player_id,))
            if cursor.rowcount == 0:
                raise HTTPException(status_code=404, detail="Player not found")
        conn.commit()
        return {"status": "success", "message": "Player reactivated"}
    except HTTPException:
        raise
    except Exception as e:
        conn.rollback()
        return {"status": "error", "message": str(e)}
    finally:
        conn.close()


@app.delete("/api/players/{player_id}")
def delete_player(player_id: int):
    """Soft delete a player. Preserves their chests."""
    conn = get_db()
    try:
        with conn.cursor() as cursor:
            cursor.execute("UPDATE players SET is_active = FALSE WHERE id = %s", (player_id,))
            if cursor.rowcount == 0:
                raise HTTPException(status_code=404, detail="Player not found")
        conn.commit()
        return {"status": "success", "message": "Player archived"}
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
def get_analytics(offset: int = 0):
    """Retrieve all data needed for the advanced analytics dashboard."""
    conn = get_db()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            # Determine target week
            from datetime import timedelta, date
            today = date.today()
            start_of_this_week = today - timedelta(days=today.weekday())
            target_week_start = start_of_this_week - timedelta(weeks=offset)
            target_week_end = target_week_start + timedelta(days=7)
            week_label = f"{target_week_start.strftime('%d %b')} - {(target_week_end - timedelta(days=1)).strftime('%d %b')}"

            # 1. Get weekly goal
            cursor.execute("SELECT value FROM settings WHERE key = 'weekly_goal'")
            setting_row = cursor.fetchone()
            weekly_goal = int(setting_row['value']) if setting_row else 700
            
            # 2. Get Targets & Summary (Selected Week)
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
                    WHERE acquired_at >= %s AND acquired_at < %s
                )
                SELECT 
                    p.username,
                    COALESCE(SUM(c.dynamic_points), 0) AS total_score,
                    COUNT(c.player_id) as chests
                FROM players p
                LEFT JOIN calculated_logs c ON p.id = c.player_id
                WHERE p.is_active = TRUE
                GROUP BY p.username
                ORDER BY total_score DESC
            """
            cursor.execute(query_stats, (target_week_start, target_week_end))
            player_stats = cursor.fetchall()
            
            total_score = sum(p['total_score'] for p in player_stats)
            total_chests = sum(p['chests'] for p in player_stats)
            
            known_players = [p for p in player_stats if p['username'] not in ('Unknown Player', 'Clan')]
            active_players = len(known_players)
            total_goal = weekly_goal * active_players if active_players > 0 else weekly_goal
            
            on_track_players = []
            needs_attention_players = []
            
            for p in known_players:
                score = p['total_score']
                diff = score - weekly_goal
                player_data = {
                    "username": p['username'],
                    "score": score,
                    "goal": weekly_goal,
                    "diff": diff
                }
                if score >= weekly_goal - 500:
                    on_track_players.append(player_data)
                else:
                    needs_attention_players.append(player_data)
            
            # 3. Get Trends (Daily for selected week)
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
                    WHERE acquired_at >= %s AND acquired_at < %s
                )
                SELECT 
                    TO_CHAR(date_trunc('day', acquired_at), 'MM-DD') as time_label,
                    COUNT(*) as chests,
                    SUM(dynamic_points) as score
                FROM calculated_logs
                GROUP BY date_trunc('day', acquired_at)
                ORDER BY date_trunc('day', acquired_at)
            """
            cursor.execute(query_daily, (target_week_start, target_week_end))
            daily_trends = cursor.fetchall()
            
            # 4. Get Sources (Using static ranges as before or maybe just for selected week?)
            def get_sources(start_d, end_d):
                query = """
                    SELECT 
                        CASE 
                            WHEN source ILIKE '%%crypt%%' THEN 'Crypts'
                            WHEN source ILIKE '%%citadel%%' THEN 'Citadels'
                            WHEN source ILIKE '%%monster%%' THEN 'Monsters'
                            WHEN source ILIKE '%%event%%' OR source ILIKE '%%triumphal%%' THEN 'Events'
                            WHEN source ILIKE '%%clan wealth%%' THEN 'Clan'
                            WHEN source ILIKE '%%arena%%' THEN 'Arena'
                            ELSE 'Resources'
                        END as category,
                        COUNT(*) as count
                    FROM chest_logs
                    WHERE acquired_at >= %s AND acquired_at < %s
                    GROUP BY category
                    ORDER BY count DESC
                """
                cursor.execute(query, (start_d, end_d))
                return cursor.fetchall()

            sources = {
                "daily": get_sources(today, today + timedelta(days=1)),
                "weekly": get_sources(target_week_start, target_week_end),
                "monthly": get_sources(today - timedelta(days=30), today + timedelta(days=1))
            }

            return {
                "status": "success", 
                "data": {
                    "week_label": week_label,
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
                        "daily": daily_trends
                    },
                    "sources": sources
                }
            }
    except Exception as e:
        return {"status": "error", "message": str(e)}
    finally:
        conn.close()



# --- REPORT GENERATION ENDPOINTS ---
from fastapi.responses import PlainTextResponse
from datetime import date, datetime, timedelta, timezone

def format_points_k(points: int) -> str:
    if points >= 1000:
        formatted = f"{points/1000:.1f}K"
        if formatted.endswith(".0K"):
            formatted = f"{points//1000}K"
        return formatted
    return str(points)

def get_weekly_date_range(offset: int = 0):
    today = date.today()
    start_of_this_week = today - timedelta(days=today.weekday())
    start_date = start_of_this_week - timedelta(days=7 * (offset + 1))
    end_date = start_date + timedelta(days=7)
    return start_date, end_date

@app.get("/api/reports/normal-weekly")
def download_normal_weekly_report(offset: int = 0):
    start_date, end_date = get_weekly_date_range(offset)
    file_name = f"weekly_report_{start_date.strftime('%d%b')}_{end_date.strftime('%d%b')}.txt"
    
    query = """
        WITH calculated_logs AS (
            SELECT 
                player_id,
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
            WHERE acquired_at >= %s AND acquired_at < %s
        )
        SELECT 
            p.username,
            COALESCE(SUM(c.dynamic_points), 0) AS total_score
        FROM players p
        LEFT JOIN calculated_logs c ON p.id = c.player_id
        WHERE p.is_active = TRUE AND p.username NOT IN ('Unknown Player', 'Clan')
        GROUP BY p.username
        ORDER BY total_score DESC
    """
    
    conn = get_db()
    lines = [f"Normal Weekly Contributions: {start_date.strftime('%d %b %Y')} to {(end_date - timedelta(days=1)).strftime('%d %b %Y')}", "="*60 + "\n"]
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(query, (start_date, end_date))
            results = cursor.fetchall()
            if not results:
                lines.append("No active players found for this period.")
            else:
                for row in results:
                    lines.append(f"{row['username']}-{format_points_k(row['total_score'])}")
    except Exception as e:
        return PlainTextResponse(f"Error generating report: {e}", status_code=500)
    finally:
        conn.close()
        
    return PlainTextResponse(content="\n".join(lines), headers={"Content-Disposition": f'attachment; filename="{file_name}"'})


@app.get("/api/reports/pure-crypting")
def download_pure_crypting_report(offset: int = 0):
    start_date, end_date = get_weekly_date_range(offset)
    file_name = f"pure_crypting_report_{start_date.strftime('%d%b')}_{end_date.strftime('%d%b')}.txt"
    
    query = """
        WITH calculated_logs AS (
            SELECT 
                player_id,
                CASE 
                    WHEN chest_type = 'common' THEN 
                        CASE chest_level WHEN 5 THEN 0 WHEN 10 THEN 1 WHEN 15 THEN 5 WHEN 20 THEN 15 WHEN 25 THEN 30 WHEN 30 THEN 60 ELSE 0 END
                    WHEN chest_type = 'rare' THEN
                        CASE chest_level WHEN 10 THEN 1 WHEN 15 THEN 5 WHEN 20 THEN 20 WHEN 25 THEN 35 WHEN 30 THEN 65 ELSE 0 END
                    WHEN chest_type = 'epic' THEN
                        CASE chest_level WHEN 5 THEN 0 WHEN 10 THEN 5 WHEN 15 THEN 10 WHEN 20 THEN 25 WHEN 25 THEN 50 WHEN 30 THEN 80 WHEN 35 THEN 140 ELSE 0 END
                    ELSE 0
                END as dynamic_points
            FROM chest_logs
            WHERE acquired_at >= %s AND acquired_at < %s AND chest_type IN ('common', 'rare', 'epic')
        )
        SELECT 
            p.username,
            COALESCE(SUM(c.dynamic_points), 0) AS pure_score
        FROM players p
        LEFT JOIN calculated_logs c ON p.id = c.player_id
        WHERE p.is_active = TRUE AND p.username NOT IN ('Unknown Player', 'Clan')
        GROUP BY p.username
        ORDER BY pure_score DESC
    """
    
    conn = get_db()
    lines = [f"Pure Crypting Weekly Report: {start_date.strftime('%d %b %Y')} to {(end_date - timedelta(days=1)).strftime('%d %b %Y')}", "="*60 + "\n"]
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(query, (start_date, end_date))
            results = cursor.fetchall()
            if not results:
                lines.append("No active players found for this period.")
            else:
                for row in results:
                    lines.append(f"{row['username']}-{format_points_k(row['pure_score'])}")
    except Exception as e:
        return PlainTextResponse(f"Error generating report: {e}", status_code=500)
    finally:
        conn.close()
        
    return PlainTextResponse(content="\n".join(lines), headers={"Content-Disposition": f'attachment; filename="{file_name}"'})


def get_event_participation(pattern: str, duration_days: float):
    """
    Finds the start time of the most recent event occurrence (last 14 days) matching pattern,
    defines window [start, start + duration_days], and returns participation status per active player.
    """
    conn = get_db()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            # 1. Find start time of most recent event
            cursor.execute("""
                SELECT MIN(acquired_at) as event_start
                FROM chest_logs
                WHERE (source ILIKE %s OR chest_title ILIKE %s)
                  AND acquired_at >= NOW() - INTERVAL '14 days'
            """, (f"%{pattern}%", f"%{pattern}%"))
            row = cursor.fetchone()
            event_start = row['event_start'] if row else None
            
            if not event_start:
                # No event recorded in last 14 days
                cursor.execute("SELECT username FROM players WHERE is_active = TRUE AND username NOT IN ('Unknown Player', 'Clan') ORDER BY username ASC")
                players = cursor.fetchall()
                return {
                    "event_name": pattern,
                    "event_start": None,
                    "event_end": None,
                    "data": [{"username": p['username'], "participated": "No", "chest_count": 0} for p in players]
                }
                
            event_end = event_start + timedelta(days=duration_days)
            
            # 2. Get player participation inside this window
            cursor.execute("""
                SELECT 
                    p.username,
                    COUNT(c.id) as chest_count
                FROM players p
                LEFT JOIN chest_logs c ON p.id = c.player_id 
                    AND (c.source ILIKE %s OR c.chest_title ILIKE %s)
                    AND c.acquired_at >= %s AND c.acquired_at <= %s
                WHERE p.is_active = TRUE AND p.username NOT IN ('Unknown Player', 'Clan')
                GROUP BY p.username
                ORDER BY p.username ASC
            """, (f"%{pattern}%", f"%{pattern}%", event_start, event_end))
            results = cursor.fetchall()
            
            data = []
            for r in results:
                cnt = r['chest_count']
                data.append({
                    "username": r['username'],
                    "participated": "Yes" if cnt > 0 else "No",
                    "chest_count": cnt
                })
                
            return {
                "event_name": pattern,
                "event_start": event_start.isoformat() if isinstance(event_start, datetime) else str(event_start),
                "event_end": event_end.isoformat() if isinstance(event_end, datetime) else str(event_end),
                "data": data
            }
    finally:
        conn.close()


@app.get("/api/reports/olympus-participation")
def download_olympus_report():
    part = get_event_participation("Hermes", duration_days=5.0)
    lines = ["Olympus Store (Hermes) Participation Report", "="*50]
    if part["event_start"]:
        lines.append(f"Event Window: {part['event_start'][:16]} to {part['event_end'][:16]}\n")
    else:
        lines.append("Event Window: No recent Hermes chests logged in last 14 days\n")
        
    lines.append("Player Name | Bought?")
    lines.append("-" * 30)
    for row in part["data"]:
        lines.append(f"{row['username']} | {row['participated']}")
        
    return PlainTextResponse(content="\n".join(lines), headers={"Content-Disposition": 'attachment; filename="olympus_participation.txt"'})


@app.get("/api/reports/ragnarok-participation")
def download_ragnarok_report():
    part = get_event_participation("Jormungandr", duration_days=2.0)
    lines = ["Ragnarok (Jormungandr) Participation Report", "="*50]
    if part["event_start"]:
        lines.append(f"Event Window: {part['event_start'][:16]} to {part['event_end'][:16]}\n")
    else:
        lines.append("Event Window: No recent Jormungandr chests logged in last 14 days\n")
        
    lines.append("Player Name | Bought?")
    lines.append("-" * 30)
    for row in part["data"]:
        lines.append(f"{row['username']} | {row['participated']}")
        
    return PlainTextResponse(content="\n".join(lines), headers={"Content-Disposition": 'attachment; filename="ragnarok_participation.txt"'})


@app.get("/api/reports/ancients-participation")
def download_ancients_report():
    part = get_event_participation("ancients", duration_days=1.0)
    lines = ["Rise of Ancients Participation Report", "="*50]
    if part["event_start"]:
        lines.append(f"Event Window: {part['event_start'][:16]} to {part['event_end'][:16]}\n")
    else:
        lines.append("Event Window: No recent Ancient chests logged in last 14 days\n")
        
    lines.append("Player Name | Participated?")
    lines.append("-" * 30)
    for row in part["data"]:
        lines.append(f"{row['username']} | {row['participated']}")
        
    return PlainTextResponse(content="\n".join(lines), headers={"Content-Disposition": 'attachment; filename="ancients_participation.txt"'})


@app.get("/api/reports/preview")
def get_reports_preview(offset: int = 0):
    """Provides JSON preview data for all reports to display on the Reports Page."""
    start_date, end_date = get_weekly_date_range(offset)
    olympus = get_event_participation("Hermes", 5.0)
    ragnarok = get_event_participation("Jormungandr", 2.0)
    ancients = get_event_participation("ancients", 1.0)
    
    return {
        "status": "success",
        "timeframe": f"{start_date.strftime('%d %b %Y')} - {(end_date - timedelta(days=1)).strftime('%d %b %Y')}",
        "olympus": olympus,
        "ragnarok": ragnarok,
        "ancients": ancients
    }


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
