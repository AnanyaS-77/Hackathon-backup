"""
Generate a secure ADMIN_PASSWORD_HASH value for production deployments.

Usage:
    python3 hash_admin_password.py "my-admin-password"
"""

import sys

from werkzeug.security import generate_password_hash


def main():
    if len(sys.argv) != 2:
        raise SystemExit('Usage: python3 hash_admin_password.py "your-admin-password"')

    password = sys.argv[1].strip()
    if not password:
        raise SystemExit("Password must not be empty.")

    print(generate_password_hash(password))


if __name__ == "__main__":
    main()
