import sqlite3
from passlib.context import CryptContext
import os

# Load .env manually
env_path = '.env'
password = None
username = 'admin'
if os.path.exists(env_path):
    with open(env_path, 'r', encoding='utf-8') as f:
        for line in f:
            if line.strip().startswith('FIRST_SUPERUSER_PASSWORD='):
                password = line.strip().split('=', 1)[1]
            if line.strip().startswith('FIRST_SUPERUSER='):
                username = line.strip().split('=', 1)[1]

if not password:
    print('NO_PASSWORD_IN_ENV')
    raise SystemExit(1)

ctx = CryptContext(schemes=['pbkdf2_sha256'], deprecated='auto')
new_hash = ctx.hash(password)

conn = sqlite3.connect('ruggylab_os.db')
cur = conn.cursor()
try:
    cur.execute('SELECT id FROM users WHERE username=?', (username,))
    row = cur.fetchone()
    if not row:
        print('NO_USER', username)
    else:
        cur.execute('UPDATE users SET hashed_password=? WHERE username=?', (new_hash, username))
        conn.commit()
        print('UPDATED', username)
        print('NEW_HASH', new_hash)
except Exception as e:
    print('ERROR', e)
finally:
    conn.close()
