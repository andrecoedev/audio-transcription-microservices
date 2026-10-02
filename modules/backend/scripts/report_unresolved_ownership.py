"""Report legacy ownership rows that could not be mapped to a persistent user."""

import argparse
import json

from sqlalchemy import func

from src.database import SessionLocal
from src.models import Transcription, TranscriptionOwnership, User


def audit_ownership(db, *, apply_exact: bool = False) -> dict:
    """Only unique, exact usernames may be backfilled; never guess ownership."""
    total = db.query(func.count(TranscriptionOwnership.id)).scalar()
    with_owner_sub = db.query(func.count(TranscriptionOwnership.id)).filter(
        TranscriptionOwnership.owner_sub.is_not(None)
    ).scalar()
    duplicate_usernames = (
        db.query(User.username)
        .group_by(User.username)
        .having(func.count(User.id) > 1)
        .count()
    )
    conflicting_matches = (
        db.query(func.count(TranscriptionOwnership.id))
        .join(User, TranscriptionOwnership.owner_sub == User.username)
        .filter(
            TranscriptionOwnership.user_id.is_not(None),
            TranscriptionOwnership.user_id != User.id,
        )
        .scalar()
    )
    orphan_user_ids = (
        db.query(func.count(TranscriptionOwnership.id))
        .outerjoin(User, TranscriptionOwnership.user_id == User.id)
        .filter(TranscriptionOwnership.user_id.is_not(None), User.id.is_(None))
        .scalar()
    )
    orphan_transcription_ids = (
        db.query(func.count(TranscriptionOwnership.id))
        .outerjoin(
            Transcription,
            TranscriptionOwnership.transcription_id == Transcription.id,
        )
        .filter(Transcription.id.is_(None))
        .scalar()
    )
    matches = (
        db.query(TranscriptionOwnership, User)
        .join(User, TranscriptionOwnership.owner_sub == User.username)
        .filter(TranscriptionOwnership.user_id.is_(None))
        .all()
    )
    if apply_exact:
        if duplicate_usernames:
            raise RuntimeError("Cannot backfill ownership with duplicate usernames")
        for ownership, user in matches:
            ownership.user_id = user.id
        db.commit()
    with_user_id = db.query(func.count(TranscriptionOwnership.id)).filter(
        TranscriptionOwnership.user_id.is_not(None)
    ).scalar()
    unresolved = (
        db.query(TranscriptionOwnership)
        .filter(TranscriptionOwnership.user_id.is_(None))
        .order_by(TranscriptionOwnership.id)
        .all()
    )
    unknown = (
        db.query(TranscriptionOwnership)
        .outerjoin(User, TranscriptionOwnership.owner_sub == User.username)
        .filter(TranscriptionOwnership.user_id.is_(None), User.id.is_(None))
        .all()
    )
    return {
        "total": total,
        "with_user_id": with_user_id,
        "with_owner_sub": with_owner_sub,
        "exact_matches": len(matches),
        "applied": len(matches) if apply_exact else 0,
        "unknown_rows": len(unknown),
        "unknown_subject_count": len({row.owner_sub for row in unknown}),
        "duplicate_usernames": duplicate_usernames,
        "conflicting_matches": conflicting_matches,
        "orphan_user_ids": orphan_user_ids,
        "orphan_transcription_ids": orphan_transcription_ids,
        "unresolved_count": len(unresolved),
        "ownership_ids": [row.id for row in unresolved],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--include-subjects",
        action="store_true",
        help="Include legacy usernames (personal data) in operator output",
    )
    parser.add_argument(
        "--apply-exact",
        action="store_true",
        help="Backfill only exact, unique username matches",
    )
    args = parser.parse_args()
    db = SessionLocal()
    try:
        result = audit_ownership(db, apply_exact=args.apply_exact)
        if args.include_subjects:
            rows = db.query(TranscriptionOwnership).filter(
                TranscriptionOwnership.user_id.is_(None)
            ).all()
            result["legacy_subjects"] = sorted({row.owner_sub for row in rows})
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 1 if result["unresolved_count"] else 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
