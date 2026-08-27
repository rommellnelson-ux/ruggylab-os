"""Verify an interactively entered password against a supplied password hash."""

from __future__ import annotations

import argparse
import getpass

from passlib.context import CryptContext


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("password_hash", help="Passlib password hash to verify")
    args = parser.parse_args()

    password = getpass.getpass("Password: ")
    context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")
    print(f"verified={context.verify(password, args.password_hash)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
