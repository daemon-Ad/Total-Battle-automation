import os
from dotenv import load_dotenv
import psycopg2
import hashlib

load_dotenv()

DB_HOST = os.getenv("DB_HOST", "localhost")
DB_NAME = os.getenv("DB_NAME", "tb_automation")
DB_USER = os.getenv("DB_USER", "tb_user")
DB_PASS = os.getenv("DB_PASS", "tb_pass")
DB_PORT = os.getenv("DB_PORT", "5432")

def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()

def update_passwords():
    conn = psycopg2.connect(
        host=DB_HOST,
        database=DB_NAME,
        user=DB_USER,
        password=DB_PASS,
        port=DB_PORT
    )
    try:
        with conn.cursor() as cursor:
            updates = [
                ("Shanks", hash_password("shanks123")),
                ("Overlord", hash_password("overlord123")),
                ("Serena", hash_password("serena123"))
            ]
            for user, phash in updates:
                cursor.execute("UPDATE users SET password_hash = %s WHERE username = %s", (phash, user))
        conn.commit()
        print("Passwords updated successfully.")
    except Exception as e:
        print(f"Error: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    update_passwords()
