"""Interactively verify an administrator password in a local SQLite database."""

from __future__ import annotations

import argparse
import getpass
import sqlite3

from passlib.context import CryptContext


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("database", help="Path to the local SQLite database")
    parser.add_argument("--username", default="admin")
    args = parser.parse_args()

    password = getpass.getpass("Password: ")
    context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")
    with sqlite3.connect(args.database) as connection:
        row = connection.execute(
            "SELECT username, hashed_password FROM users WHERE username = ?",
            (args.username,),
        ).fetchone()

    if row is None:
        print("User not found.")
        return 1

    verified = context.verify(password, row[1])
    print(f"verified={verified}")
    return 0 if verified else 1


if __name__ == "__main__":
    raise SystemExit(main())
