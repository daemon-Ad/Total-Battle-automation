import os
from db import get_connection
from datetime import date, timedelta
from psycopg2.extras import RealDictCursor

def generate_report():
    today = date.today()
    # Monday is 0. Find the start of THIS week.
    start_of_this_week = today - timedelta(days=today.weekday())
    # Previous week
    start_date = start_of_this_week - timedelta(days=7)
    end_date = start_of_this_week
    
    file_name = f"weekly_report_{start_date.strftime('%d%b')}_{end_date.strftime('%d%b')}.txt"
    filepath = os.path.join(os.path.dirname(os.path.abspath(__file__)), file_name)
    
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
    
    conn = get_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(query, (start_date, end_date))
            results = cursor.fetchall()
            
            with open(filepath, 'w') as f:
                f.write(f"Clan Weekly Contributions: {start_date.strftime('%d %b %Y')} to {(end_date - timedelta(days=1)).strftime('%d %b %Y')}\n")
                f.write("="*60 + "\n\n")
                
                if not results:
                    f.write("No active players found for this period.\n")
                
                for row in results:
                    points = row['total_score']
                    if points >= 1000:
                        formatted_points = f"{points/1000:.1f}k"
                        if formatted_points.endswith(".0k"):
                            formatted_points = f"{points//1000}k"
                    else:
                        formatted_points = str(points)
                        
                    f.write(f"{row['username']}: {formatted_points}\n")
            
            print(f"Report generated successfully: {file_name}")
    except Exception as e:
        print(f"Error generating report: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    generate_report()
