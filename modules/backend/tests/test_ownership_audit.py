from scripts.report_unresolved_ownership import audit_ownership
from src.models import Transcription, TranscriptionOwnership


def test_exact_ownership_audit_preserves_unknown_legacy_rows(db_context):
    db = db_context["session_factory"]()
    try:
        for owner_sub in ("alice", "someone-else"):
            transcription = Transcription(
                filename="old.wav",
                original_filename="old.wav",
                file_size_mb=1,
                duration_seconds=1,
                transcription_model="whisper",
                segments=[],
                status="completed",
            )
            db.add(transcription)
            db.flush()
            db.add(TranscriptionOwnership(
                transcription_id=transcription.id, owner_sub=owner_sub
            ))
        db.commit()
        preview = audit_ownership(db)
        assert preview["total"] == 2
        assert preview["with_user_id"] == 0
        assert preview["with_owner_sub"] == 2
        assert preview["exact_matches"] == 1
        assert preview["unknown_rows"] == 1
        assert preview["unknown_subject_count"] == 1
        assert preview["duplicate_usernames"] == 0
        assert preview["conflicting_matches"] == 0
        assert preview["orphan_user_ids"] == 0
        assert preview["orphan_transcription_ids"] == 0
        assert preview["unresolved_count"] == 2
        applied = audit_ownership(db, apply_exact=True)
        assert applied["applied"] == 1
        assert applied["with_user_id"] == 1
        assert applied["unresolved_count"] == 1
        assert audit_ownership(db, apply_exact=True)["applied"] == 0
        owner = db.query(TranscriptionOwnership).filter_by(
            owner_sub="someone-else"
        ).one()
        assert owner.user_id is None
        alice_owner = db.query(TranscriptionOwnership).filter_by(owner_sub="alice").one()
        alice_owner.user_id = 2
        db.commit()
        conflict_report = audit_ownership(db)
        assert conflict_report["conflicting_matches"] == 1
        assert conflict_report["orphan_user_ids"] == 0
    finally:
        db.close()
