from db import get_connection, hash_password

def update_admins():
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT username FROM players WHERE rank IN ('Leader', 'Superior')")
    admins = c.fetchall()
    
    passwords = []
    
    for row in admins:
        uname = row[0]
        pwd = f"tb1234"
        c.execute("SELECT id FROM users WHERE username = %s", (uname,))
        if not c.fetchone():
            c.execute("INSERT INTO users (username, password_hash) VALUES (%s, %s)", (uname, hash_password(pwd)))
            passwords.append(f"{uname}: {pwd}")
    
    conn.commit()
    conn.close()
    
    print("New Admin Passwords:")
    for p in passwords:
        print(p)

if __name__ == '__main__':
    update_admins()
