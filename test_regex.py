import re

tests = [
    "Bih 28m",
    "Xih 29m",
    "1h 30m",
    "45m 12s",
    "hourglass 3h 45m"
]

for t in tests:
    clean = t.lower().replace('i', '1').replace('l', '1').replace('o', '0')
    matches = re.findall(r'\d+[hms]', clean)
    print(f"Original: {t} -> Clean: {clean} -> Final: {' '.join(matches)}")
