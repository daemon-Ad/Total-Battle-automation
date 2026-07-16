import re
from datetime import datetime, timedelta, timezone

def parse_timer_to_timedelta(timer_str: str) -> timedelta:
    """
    Parses a string like '3h 45m' or '45m 10s' into a timedelta.
    """
    hours, minutes, seconds = 0, 0, 0
    
    # Extract digits before 'h', 'm', 's'
    h_match = re.search(r'(\d+)h', timer_str)
    m_match = re.search(r'(\d+)m', timer_str)
    s_match = re.search(r'(\d+)s', timer_str)
    
    if h_match:
        hours = int(h_match.group(1))
    if m_match:
        minutes = int(m_match.group(1))
    if s_match:
        seconds = int(s_match.group(1))
        
    return timedelta(hours=hours, minutes=minutes, seconds=seconds)

def calculate_acquired_time(timer_str: str) -> datetime:
    """
    Calculates the exact UTC timestamp the chest was acquired.
    TTL is 20 hours. remaining_time = timer_str.
    acquired_at = current_utc - (20h - remaining_time)
    """
    current_utc = datetime.now(timezone.utc)
    
    if not timer_str:
        return current_utc
        
    remaining_time = parse_timer_to_timedelta(timer_str)
    max_ttl = timedelta(hours=20)
    
    # gap2 = 20h - remaining_time
    # This represents how long ago the chest was acquired
    gap2 = max_ttl - remaining_time
    
    # If for some reason OCR parses > 20h, just return current time
    if gap2.total_seconds() < 0:
        gap2 = timedelta(0)
        
    acquired_at = current_utc - gap2
    
    return acquired_at

def get_game_date(acquired_at: datetime):
    """
    Returns the 'Game Date' for a given timestamp.
    Game days reset at 17:00 UTC. 
    So any time before 17:00 belongs to the previous calendar day relative to acquired_at.
    """
    if acquired_at.hour >= 17:
        return acquired_at.date()
    else:
        return acquired_at.date() - timedelta(days=1)
