"""Create a persistent local user without putting a password in shell history."""

import argparse
import getpass

from sqlalchemy.exc import IntegrityError

from src.database import SessionLocal
from src.models import User
from src.security import get_password_hash


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--username", required=True)
    parser.add_argument("--email", required=True)
    parser.add_argument("--admin", action="store_true")
    args = parser.parse_args()
    password = getpass.getpass("Password: ")
    confirmation = getpass.getpass("Confirm password: ")
    if password != confirmation:
        parser.error("passwords do not match")

    db = SessionLocal()
    try:
        db.add(
            User(
                username=args.username.strip(),
                email=args.email.strip().lower(),
                hashed_password=get_password_hash(password),
                is_active=True,
                is_superuser=args.admin,
            )
        )
        db.commit()
        print("Local user created")
        return 0
    except IntegrityError as exc:
        db.rollback()
        parser.error(f"username or email already exists: {exc.__class__.__name__}")
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
