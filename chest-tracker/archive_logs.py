import sys
import os
from psycopg2.extras import RealDictCursor

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from db import get_connection, setup_schema, archive_old_chest_logs

def get_combined_totals():
    conn = get_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute("""
                SELECT
                    (SELECT COALESCE(SUM(points), 0) FROM chest_logs) +
                    (SELECT COALESCE(SUM(total_points), 0) FROM chest_logs_monthly_summary) AS all_time_points,
                    (SELECT COUNT(*) FROM chest_logs) +
                    (SELECT COALESCE(SUM(total_chests), 0) FROM chest_logs_monthly_summary) AS all_time_chests,
                    (SELECT COUNT(*) FROM chest_logs) AS active_logs_count,
                    (SELECT COUNT(*) FROM chest_logs_monthly_summary) AS summary_months_count;
            """)
            return cursor.fetchone()
    finally:
        conn.close()

def main():
    setup_schema()

    print("=== Pre-Archival State ===")
    pre = get_combined_totals()
    print(f"Active chest_logs count: {pre['active_logs_count']}")
    print(f"Summary months count:    {pre['summary_months_count']}")
    print(f"All-Time Total Points:   {pre['all_time_points']:,}")
    print(f"All-Time Total Chests:   {pre['all_time_chests']:,}")

    print(f"\nArchiving raw logs older than 30 days...")
    archived_chests, archived_points = archive_old_chest_logs()
    print(f"Archived: {archived_chests:,} chests ({archived_points:,} points) and purged raw log entries.")

    print("\n=== Post-Archival State ===")
    post = get_combined_totals()
    print(f"Active chest_logs count: {post['active_logs_count']}")
    print(f"Summary months count:    {post['summary_months_count']}")
    print(f"All-Time Total Points:   {post['all_time_points']:,}")
    print(f"All-Time Total Chests:   {post['all_time_chests']:,}")

    # Integrity verification
    if pre['all_time_points'] == post['all_time_points'] and pre['all_time_chests'] == post['all_time_chests']:
        print("\n[VERIFICATION SUCCESSFUL] All-time totals match perfectly before and after archival!")
    else:
        print("\n[WARNING] Mismatch detected in all-time totals!", file=sys.stderr)

if __name__ == "__main__":
    main()
