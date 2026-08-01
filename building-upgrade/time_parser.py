import re

def parse_march_time_seconds(text):
    """Parses march time strings like '1m 02s', '1h 2m 3s', or '100d 17h' into total seconds."""
    text = text.lower()
    
    # Fix common OCR mistakes
    text = text.replace('o', '0').replace('g', '9').replace('l', '1')
    
    d_match = re.search(r"(\d+)\s*d", text)
    h_match = re.search(r"(\d+)\s*h", text)
    m_match = re.search(r"(\d+)\s*m(?!s)", text)
    
    total = 0
    if d_match:
        total += int(d_match.group(1)) * 86400
    if h_match:
        total += int(h_match.group(1)) * 3600
    if m_match:
        total += int(m_match.group(1)) * 60
        
    s_match = re.search(r"(\d+)\s*s(?!\w)", text)
    if s_match:
        total += int(s_match.group(1))
    elif m_match:
        after_m = text[m_match.end():]
        s_5_match = re.search(r"^\s*(\d+)\s*5(?!\d)", after_m)
        if s_5_match:
            total += int(s_5_match.group(1))
            
    return total if total > 0 else None
