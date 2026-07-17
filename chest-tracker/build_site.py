import os
import json
from psycopg2.extras import RealDictCursor
from db import get_connection

OUTPUT_DIR = "dashboard/api"

def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    os.makedirs(os.path.join(OUTPUT_DIR, "chests"), exist_ok=True)
    
    conn = get_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            # 1. PLAYERS
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
            with open(os.path.join(OUTPUT_DIR, "players.json"), "w") as f:
                json.dump({"status": "success", "data": players}, f)
            
            # 2. LEADERBOARD
            cursor.execute("""
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
                GROUP BY p.id, p.username
                ORDER BY total_score DESC NULLS LAST
            """)
            leaderboard = cursor.fetchall()
            with open(os.path.join(OUTPUT_DIR, "leaderboard.json"), "w") as f:
                json.dump({"status": "success", "data": leaderboard}, f)
            
            # 3. ANALYTICS
            # We calculate this manually based on the leaderboard data
            total_score_all = sum(row['total_score'] for row in leaderboard)
            total_members = len(leaderboard)
            weekly_goal_per_player = 1000 # Default from old settings
            
            # check if settings exists in db
            cursor.execute("SELECT value FROM settings WHERE key = 'weekly_goal'")
            settings = cursor.fetchone()
            if settings:
                weekly_goal_per_player = int(settings['value'])
            
            total_goal_all = total_members * weekly_goal_per_player
            
            on_track_count = sum(1 for row in leaderboard if row['total_score'] >= weekly_goal_per_player)
            needs_attention_count = total_members - on_track_count
            
            # For the lists
            on_track_list = []
            needs_attention_list = []
            
            for row in leaderboard:
                diff = row['total_score'] - weekly_goal_per_player
                p_dict = {
                    "username": row['username'],
                    "score": row['total_score'],
                    "goal": weekly_goal_per_player,
                    "diff": diff
                }
                if row['total_score'] >= weekly_goal_per_player:
                    on_track_list.append(p_dict)
                else:
                    needs_attention_list.append(p_dict)
                    
            on_track_list.sort(key=lambda x: x['diff'], reverse=True)
            needs_attention_list.sort(key=lambda x: x['diff']) # lowest first
            
            analytics_data = {
                "targets": {
                    "total_score": total_score_all,
                    "total_goal": total_goal_all
                },
                "summary": {
                    "on_track_count": on_track_count,
                    "needs_attention_count": needs_attention_count,
                    "total_members": total_members
                },
                "lists": {
                    "on_track": on_track_list[:10],
                    "needs_attention": needs_attention_list[:10]
                }
            }
            with open(os.path.join(OUTPUT_DIR, "analytics.json"), "w") as f:
                json.dump({"status": "success", "data": analytics_data}, f)
                
            # 4. INDIVIDUAL CHESTS
            for p in players:
                cursor.execute("""
                    SELECT 
                        id,
                        chest_type,
                        chest_level,
                        CASE 
                            WHEN chest_type = 'common' THEN 
                                CASE chest_level WHEN 5 THEN 0 WHEN 10 THEN 1 WHEN 15 THEN 5 WHEN 20 THEN 15 WHEN 25 THEN 30 WHEN 30 THEN 60 ELSE 0 END
                            WHEN chest_type = 'rare' THEN
                                CASE chest_level WHEN 10 THEN 1 WHEN 15 THEN 5 WHEN 20 THEN 20 WHEN 25 THEN 35 WHEN 30 THEN 65 ELSE 0 END
                            WHEN chest_type IN ('epic', 'event') THEN
                                CASE chest_level WHEN 5 THEN 0 WHEN 10 THEN 5 WHEN 15 THEN 10 WHEN 20 THEN 25 WHEN 25 THEN 50 WHEN 30 THEN 80 WHEN 35 THEN 140 ELSE 0 END
                            ELSE 0
                        END as dynamic_points,
                        acquired_at
                    FROM chest_logs
                    WHERE player_id = %s
                    ORDER BY acquired_at DESC
                    LIMIT 50
                """, (p['id'],))
                chests = cursor.fetchall()
                # Need to convert datetime to string
                for c in chests:
                    if c['acquired_at']:
                        c['acquired_at'] = c['acquired_at'].isoformat()
                        
                with open(os.path.join(OUTPUT_DIR, f"chests/chests_{p['id']}.json"), "w") as f:
                    json.dump({"status": "success", "data": chests}, f)
                    
            # 5. SETTINGS
            with open(os.path.join(OUTPUT_DIR, "settings.json"), "w") as f:
                json.dump({"status": "success", "data": {"weekly_goal": weekly_goal_per_player}}, f)
                
            print(f"Generated static files in {OUTPUT_DIR}")
            
    finally:
        conn.close()

if __name__ == "__main__":
    main()
