import psycopg2
from db import get_connection, setup_schema
import difflib

LEADER = ["Serena"]
SUPERIOR = ["Le Commando FaDah", "Scarlett Orianna", "Don 23", "Kalmeena", "Fifoudu30", "Fanven", "Tony Stark", "Zololar", "DSK", "COOL 1 CP CITY G", "baby Gavarelle", "Overlord", "COOL 1 CP CITY i", "Aragorn", "BK 2 CITY"]
VETERAN = ["bidas 2", "Fracasse LiFRAnor", "GOYBI", "LINDEN II", "Diane", "bidas", "Harika", "SIBILA", "Deyernus", "Le FRAcasse Meteor", "Burilen", "Lunara", "Z E E", "FRAcasse LUCUINOU", "Celestial", "Menelas", "Aillix", "Pacotille"]
UNKNOWN = ["Clan", "Unknown"]

def update_ranks():
    setup_schema() # Ensures column exists
    
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            # First, set everyone to Officer
            cursor.execute("UPDATE players SET rank = 'Officer'")
            
            # Fetch all players to do fuzzy matching if needed
            cursor.execute("SELECT id, username FROM players")
            db_players = cursor.fetchall()
            db_names = {p[1]: p[0] for p in db_players}
            
            def set_rank(names, rank):
                for name in names:
                    if name in db_names:
                        cursor.execute("UPDATE players SET rank = %s WHERE id = %s", (rank, db_names[name]))
                    else:
                        matches = difflib.get_close_matches(name, db_names.keys(), n=1, cutoff=0.7)
                        if matches:
                            matched_name = matches[0]
                            cursor.execute("UPDATE players SET rank = %s WHERE id = %s", (rank, db_names[matched_name]))
                            print(f"Fuzzy matched '{name}' -> '{matched_name}' as {rank}")
                        else:
                            print(f"Could not find '{name}' in DB for rank {rank}")
            
            set_rank(LEADER, 'Leader')
            set_rank(SUPERIOR, 'Superior')
            set_rank(VETERAN, 'Veteran')
            set_rank(UNKNOWN, 'Unknown')
            
            # Check counts
            cursor.execute("SELECT rank, COUNT(*) FROM players GROUP BY rank")
            counts = cursor.fetchall()
            print("Rank distribution:")
            for r, c in counts:
                print(f"{r}: {c}")
                
        conn.commit()
    finally:
        conn.close()

if __name__ == "__main__":
    update_ranks()
