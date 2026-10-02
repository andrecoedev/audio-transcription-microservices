"""Dry-run-first application of configured database retention policies."""

import argparse
import json

from src.database import SessionLocal
from src.services.storage_lifecycle import apply_database_retention
from src.services.guest_retention import apply_guest_retention


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    db = SessionLocal()
    try:
        result = apply_database_retention(db, apply=args.apply)
        result["guest"] = apply_guest_retention(db, apply=args.apply)
        print(json.dumps(result, indent=2))
        return 1 if result["files_failed"] or result["guest"]["files_failed"] else 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
