"""Dry-run-first Firebase erasure retry, run ONLY in the API credential context."""
import argparse
import json

from src.database import SessionLocal
from src.services.account_deletion import retry_identity_cleanup


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--limit", type=int, default=100)
    args = parser.parse_args()
    if not 1 <= args.limit <= 1000:
        parser.error("--limit must be between 1 and 1000")
    with SessionLocal() as db:
        result = retry_identity_cleanup(db, apply=args.apply, limit=args.limit)
    print(json.dumps(result))  # Counts only: never UID, email, credentials, or errors.
    return 1 if args.apply and result["pending"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
