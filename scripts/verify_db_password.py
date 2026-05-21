import sqlite3

from passlib.context import CryptContext

pwd = "SuperAdmin2026!SecurePass"
ctx = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")
conn = sqlite3.connect("ruggylab_os.db")
cur = conn.cursor()
try:
    cur.execute("SELECT username, hashed_password FROM users WHERE username='admin'")
    row = cur.fetchone()
    if not row:
        print("NO_ADMIN")
    else:
        username, hashed = row
        print("HASH:", hashed)
        print("VERIFY:", ctx.verify(pwd, hashed))
except Exception as e:
    print("ERROR", e)
finally:
    conn.close()
