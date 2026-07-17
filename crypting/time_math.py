import re

def parse_march_time_seconds(text):
    """Parses march time strings like '1m 02s' or '1h 2m 3s' into total seconds."""
    # Ensure text is lowercase for easier matching
    text = text.lower()
    h_match = re.search(r"(\d+)\s*h", text)
    m_match = re.search(r"(\d+)\s*m(?!s)", text)  # avoid matching 'ms' if it ever appears
    
    total = 0
    if h_match:
        total += int(h_match.group(1)) * 3600
    if m_match:
        total += int(m_match.group(1)) * 60
        
    # Standard 's' match
    s_match = re.search(r"(\d+)\s*s(?!\w)", text)
    if s_match:
        total += int(s_match.group(1))
    elif m_match:
        # OCR might misread 's' as '5', e.g. "3m 135" -> "3m 13s"
        # Look for seconds immediately following the 'm' match to avoid matching random '5's elsewhere
        after_m = text[m_match.end():]
        s_5_match = re.search(r"^\s*(\d+)\s*5(?!\d)", after_m)
        if s_5_match:
            total += int(s_5_match.group(1))
            
    return total if total > 0 else None

def parse_tar_amount(text):
    """Parses amount like '510K', '34.7K' into an integer. Handles '1.6M/24K' by taking the first part."""
    text = text.strip().upper()
    # Replace 'O' with '0' and 'S' with '5' (common OCR errors)
    text = text.replace('O', '0').replace('S', '5')
    
    # We only want the available tar (first part before the slash)
    if '/' in text:
        text = text.split('/')[0]
        
    m = re.search(r"([\d.,]+)\s*([KMB])?", text)
    if not m:
        return None
    number_str = m.group(1).replace(",", "")
    try:
        number = float(number_str)
    except ValueError:
        return None
        
    suffix = m.group(2)
    multiplier = 1
    if suffix == 'K':
        multiplier = 1_000
    elif suffix == 'M':
        multiplier = 1_000_000
    elif suffix == 'B':
        multiplier = 1_000_000_000
        
    return int(number * multiplier)

def compute_reduced_time(initial_seconds):
    """
    Simulates using the 'Use' button which halves the time (after subtracting 1s).
    Max 5 uses, stops if time <= 20s.
    Returns: (final_seconds, uses_made)
    """
    t = float(initial_seconds)
    uses = 5
    for _ in range(5):
        if t <= 21:
            break
        t = (t + 1) / 2
    return t, uses
