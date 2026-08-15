import sys
import os
import time

# Ensure module path works
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from db import get_connection, setup_schema

def audit_and_fix_points():
    print("Setting up schema and ensuring database triggers are active...")
    setup_schema()

    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            # 1. Count total records
            cursor.execute("SELECT COUNT(*) FROM chest_logs;")
            total_records = cursor.fetchone()[0]

            # 2. Count records where current points mismatch calculated points
            cursor.execute("""
                SELECT COUNT(*) 
                FROM chest_logs 
                WHERE points IS NULL OR points != calculate_chest_points(chest_type, chest_level);
            """)
            mismatched_count = cursor.fetchone()[0]

            print(f"Total chest records in database: {total_records}")
            print(f"Records with mismatched/outdated points: {mismatched_count}")

            if mismatched_count > 0:
                print("Recalculating and updating points for mismatched records...")
                start_time = time.time()
                
                cursor.execute("""
                    UPDATE chest_logs 
                    SET points = calculate_chest_points(chest_type, chest_level)
                    WHERE points IS NULL OR points != calculate_chest_points(chest_type, chest_level);
                """)
                
                conn.commit()
                elapsed = time.time() - start_time
                print(f"Successfully updated {mismatched_count} records in {elapsed:.2f} seconds!")
            else:
                print("All chest log points are 100% accurate and up-to-date!")

    except Exception as e:
        conn.rollback()
        print(f"Error during audit and fix: {e}", file=sys.stderr)
    finally:
        conn.close()

if __name__ == "__main__":
    audit_and_fix_points()
