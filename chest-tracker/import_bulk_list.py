import sys
import os

# Ensure chest-tracker module paths work
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from db import log_chest
from points import calculate_points

RAW_DATA = """
# Paste your list below, line by line.
# Format: Player name, chest_type, chest_level, count
# Example:
# Mojora, common, 20, 10
"""

def process_line(line: str, default_date: str = "2026-08-13 09:00:00"):
    line = line.strip()
    if not line or line.startswith("#"):
        return 0

    parts = [p.strip() for p in line.split(",")]
    if len(parts) < 4:
        print(f"Skipping invalid line: {line}")
        return 0

    username = parts[0]
    chest_type = parts[1].lower()
    try:
        level = int(parts[2])
        count = int(parts[3])
    except ValueError:
        print(f"Error parsing numbers in line: {line}")
        return 0

    points = calculate_points(chest_type, level)
    
    logged = 0
    for _ in range(count):
        log_chest(
            username=username,
            title="",
            chest_type=chest_type,
            level=level,
            source="Manual Bulk Import",
            timer_text="",
            acquired_at=default_date,
            points=points
        )
        logged += 1
    
    return logged

def run_import(text_data: str):
    total = 0
    lines = text_data.strip().splitlines()
    for line in lines:
        total += process_line(line)
    print(f"\nSuccessfully imported {total} database records for 2026-08-13!")

if __name__ == "__main__":
    if len(sys.argv) > 1 and os.path.exists(sys.argv[1]):
        with open(sys.argv[1], "r") as f:
            content = f.read()
    else:
        content = RAW_DATA
    
    run_import(content)
