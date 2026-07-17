import sys
import getpass
import psycopg2
from db import get_connection, hash_password

def add_user():
    print("=== Add New Dashboard User ===")
    username = input("Enter new username: ").strip()
    if not username:
        print("Username cannot be empty.")
        sys.exit(1)
        
    password = getpass.getpass("Enter password: ")
    if not password:
        print("Password cannot be empty.")
        sys.exit(1)
        
    confirm_password = getpass.getpass("Confirm password: ")
    if password != confirm_password:
        print("Passwords do not match!")
        sys.exit(1)
        
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            # Check if user already exists
            cursor.execute("SELECT id FROM users WHERE username = %s", (username,))
            if cursor.fetchone():
                print(f"Error: User '{username}' already exists.")
                sys.exit(1)
                
            hashed_pw = hash_password(password)
            cursor.execute("INSERT INTO users (username, password_hash) VALUES (%s, %s)", (username, hashed_pw))
            conn.commit()
            print(f"\nSuccess! User '{username}' has been added to the database.")
            print("They can now log into the dashboard.")
            
    except psycopg2.Error as e:
        print(f"Database error: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    add_user()
