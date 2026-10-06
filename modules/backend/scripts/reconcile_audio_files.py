"""Dry-run-first reconciliation of stale, unreferenced upload files."""

import argparse
import json

from src.database import SessionLocal
from src.services.storage_lifecycle import reconcile_orphaned_uploads
from src.services.audio_storage import retry_audio_cleanup


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="Delete candidates")
    parser.add_argument("--older-than-hours", type=int)
    args = parser.parse_args()
    db = SessionLocal()
    try:
        result = reconcile_orphaned_uploads(
            db,
            older_than_hours=args.older_than_hours,
            apply=args.apply,
        )
        result["cleanup_retries"] = retry_audio_cleanup(db, apply=args.apply)
        print(json.dumps(result, indent=2))
        return 1 if result["failed"] or result["cleanup_retries"]["failed"] else 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
