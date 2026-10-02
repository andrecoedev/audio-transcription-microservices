"""Internal LGPD-oriented user export/erasure utility."""

import argparse
import json
from pathlib import Path

from src.database import SessionLocal
from src.models import User
from src.services.privacy import erase_user_data, export_user_data


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("export", "delete"))
    parser.add_argument("--username", required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--confirm", help="Must equal username for deletion")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.username == args.username).one_or_none()
        if user is None:
            parser.error("user not found")
        if args.action == "export":
            payload = export_user_data(db, user)
            serialized = json.dumps(payload, ensure_ascii=False, indent=2)
            if args.output:
                args.output.write_text(serialized + "\n", encoding="utf-8")
            else:
                print(serialized)
            return 0
        if args.confirm != args.username:
            parser.error("--confirm must exactly match --username")
        result = erase_user_data(db, user)
        print(json.dumps(result.__dict__, indent=2))
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
