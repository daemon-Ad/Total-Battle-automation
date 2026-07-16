def calculate_points(chest_type: str, level: int) -> int:
    """
    Calculates the point value for a given chest type and level.
    Chest types should be one of: 'common', 'rare', 'epic', 'event'.
    """
    chest_type = chest_type.lower()
    
    # Points matrix definition
    common_points = {5: 0, 10: 1, 15: 5, 20: 15, 25: 30, 30: 60}
    rare_points = {10: 1, 15: 5, 20: 20, 25: 35, 30: 65}
    epic_points = {15: 10, 20: 25, 25: 50, 30: 80, 35: 140}
    
    # Events use the exact same point scale as Epic
    # (green=10=5pts, blue=15=10pts, purple=20=25pts, orange=25=50pts, red=30=80pts, gold=35=140pts)
    # Wait, green=10 is 5pts? The Epic table doesn't have level 10!
    # Let's define the event points explicitly based on the color mapping we have:
    # white(5)=0, green(10)=5, blue(15)=10, purple(20)=25, orange(25)=50, red(30)=80, gold(35)=140
    event_points = {5: 0, 10: 5, 15: 10, 20: 25, 25: 50, 30: 80, 35: 140}

    matrix = common_points
    if chest_type == 'rare':
        matrix = rare_points
    elif chest_type in ['epic', 'event']:
        # If it's event, we use the event_points which covers level 10
        if chest_type == 'event':
            matrix = event_points
        else:
            matrix = epic_points
            
    # Lookup points, defaulting to 0 if the level is strangely missing
    return matrix.get(level, 0)
