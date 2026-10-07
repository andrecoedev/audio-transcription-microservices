"""Dry-run-first private usage replay and versioned catalog import."""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.database import SessionLocal
from src.services.usage_metering import reconcile_usage
from src.services.usage_prices import import_prices


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("replay", "prices"))
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--catalog", type=Path)
    parser.add_argument("--limit", type=int, default=1000)
    args = parser.parse_args()
    if not 1 <= args.limit <= 10000:
        parser.error("limit must be 1-10000")
    try:
        if args.operation == "replay":
            result = reconcile_usage(apply=args.apply, limit=args.limit)
        else:
            if not args.catalog or args.catalog.stat().st_size > 1000000:
                parser.error("a catalog of at most 1 MB is required")
            with SessionLocal() as db:
                result = import_prices(db, json.loads(args.catalog.read_text(encoding="utf-8")), apply=args.apply)
                if args.apply:
                    db.commit()
        print(json.dumps(result))
        return 1 if result.get("failed") else 0
    except Exception as exc:
        print(f"Usage maintenance failed ({type(exc).__name__})", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
