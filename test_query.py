import psycopg2
from psycopg2.extras import RealDictCursor
import json

conn = psycopg2.connect("dbname=chest_tracker user=postgres password=postgres")
try:
    with conn.cursor(cursor_factory=RealDictCursor) as cursor:
        cursor.execute("""
            WITH recent_chests AS (
                SELECT player_id, source, chest_title, chest_type, chest_level
                FROM chest_logs
                WHERE acquired_at >= NOW() - INTERVAL '14 days'
            ),
            player_stats AS (
                SELECT 
                    p.id,
                    p.username,
                    p.is_active,
                    -- Pure Crypting score
                    COALESCE(SUM(
                        CASE WHEN c.chest_type = 'common' THEN 
                            CASE c.chest_level WHEN 5 THEN 0 WHEN 10 THEN 1 WHEN 15 THEN 5 WHEN 20 THEN 15 WHEN 25 THEN 30 WHEN 30 THEN 60 ELSE 0 END
                        WHEN c.chest_type = 'rare' THEN
                            CASE c.chest_level WHEN 10 THEN 1 WHEN 15 THEN 5 WHEN 20 THEN 20 WHEN 25 THEN 35 WHEN 30 THEN 65 ELSE 0 END
                        WHEN c.chest_type IN ('epic', 'event') THEN
                            CASE c.chest_level WHEN 5 THEN 0 WHEN 10 THEN 5 WHEN 15 THEN 10 WHEN 20 THEN 25 WHEN 25 THEN 50 WHEN 30 THEN 80 WHEN 35 THEN 140 ELSE 0 END
                        ELSE 0 END
                    ), 0) AS pure_score,
                    
                    -- Event participation counts
                    COUNT(*) FILTER (WHERE c.source ILIKE '%Jormungandr%' OR c.chest_title ILIKE '%Jormungandr%') AS ragnarok_count,
                    COUNT(*) FILTER (WHERE c.source ILIKE '%Hermes%' OR c.chest_title ILIKE '%Hermes%') AS olympus_count,
                    COUNT(*) FILTER (WHERE c.source ILIKE '%ancients%' OR c.chest_title ILIKE '%ancients%') AS ancients_count
                FROM players p
                LEFT JOIN recent_chests c ON p.id = c.player_id
                WHERE p.username NOT IN ('Unknown Player', 'Clan') AND p.is_active = TRUE
                GROUP BY p.id, p.username, p.is_active
            )
            SELECT *,
                CASE 
                    WHEN pure_score = 0 AND ragnarok_count = 0 AND olympus_count = 0 AND ancients_count = 0 THEN 4
                    WHEN pure_score = 0 THEN 3
                    WHEN ancients_count = 0 AND olympus_count = 0 THEN 2
                    WHEN ragnarok_count = 0 THEN 1
                    ELSE 0
                END AS slacker_level
            FROM player_stats
            WHERE 
                (pure_score = 0 AND ragnarok_count = 0 AND olympus_count = 0 AND ancients_count = 0) OR
                (pure_score = 0) OR
                (ancients_count = 0 AND olympus_count = 0) OR
                (ragnarok_count = 0)
            ORDER BY slacker_level DESC, username ASC;
        """)
        results = cursor.fetchall()
        print(json.dumps([dict(r) for r in results], indent=2))
finally:
    conn.close()
