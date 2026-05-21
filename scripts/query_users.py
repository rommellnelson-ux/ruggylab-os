import json
import sqlite3

conn = sqlite3.connect("ruggylab_os.db")
cur = conn.cursor()
try:
    cur.execute("SELECT id, username, hashed_password, full_name, role FROM users")
    rows = cur.fetchall()
    print(json.dumps(rows, indent=2))
except Exception as e:
    print("ERROR", e)
finally:
    conn.close()
