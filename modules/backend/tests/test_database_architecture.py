from pathlib import Path

import pytest
from sqlalchemy import CheckConstraint, ForeignKeyConstraint, create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from src import database
from src.config import Settings
from src.models import Base, Meeting, MeetingSpeaker, ObjectDeletion, Transcription, TranscriptionJob, TranscriptionOwnership


def test_production_database_module_does_not_create_schema():
    source = Path(database.__file__).read_text(encoding="utf-8")
    assert "create_all" not in source


def test_job_and_ownership_have_cascading_foreign_keys():
    for model in (TranscriptionJob, TranscriptionOwnership):
        foreign_keys = [
            constraint
            for constraint in model.__table__.constraints
            if isinstance(constraint, ForeignKeyConstraint)
        ]
        transcription_fk = next(
            constraint
            for constraint in foreign_keys
            if next(iter(constraint.elements)).target_fullname == "transcriptions.id"
        )
        assert transcription_fk.ondelete == "CASCADE"
    user_fk = next(
        constraint
        for constraint in TranscriptionOwnership.__table__.constraints
        if isinstance(constraint, ForeignKeyConstraint)
        and next(iter(constraint.elements)).target_fullname == "users.id"
    )
    assert user_fk.ondelete == "RESTRICT"


def test_meeting_and_speakers_have_cascading_foreign_keys():
    for model, parent in ((Meeting, "transcriptions.id"), (MeetingSpeaker, "meetings.id")):
        foreign_key = next(
            constraint for constraint in model.__table__.constraints
            if isinstance(constraint, ForeignKeyConstraint)
            and next(iter(constraint.elements)).target_fullname == parent
        )
        assert foreign_key.ondelete == "CASCADE"


def test_status_constraints_exist():
    for model in (Transcription, TranscriptionJob):
        names = {
            constraint.name
            for constraint in model.__table__.constraints
            if isinstance(constraint, CheckConstraint)
        }
        assert any(name and name.endswith("_status") for name in names)


def test_object_deletion_defaults_and_constraints():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    try:
        with Session(engine) as db:
            row = ObjectDeletion(reference="objects/transcription/opaque-key")
            db.add(row)
            db.commit()
            assert row.attempts == 0
            assert row.created_at is not None
            assert row.last_attempt_at is None

            db.add(ObjectDeletion(reference=row.reference))
            with pytest.raises(IntegrityError):
                db.commit()
            db.rollback()

            db.add(ObjectDeletion(reference="legacy/audio.wav", attempts=-1))
            with pytest.raises(IntegrityError):
                db.commit()
            db.rollback()
    finally:
        Base.metadata.drop_all(engine)


def test_transcription_job_input_object_key_is_nullable_and_bounded():
    column = TranscriptionJob.__table__.c.input_object_key
    assert column.nullable
    assert column.type.length == 128


def test_get_db_rolls_back_and_closes_on_error(monkeypatch):
    events = []

    class FakeSession:
        def rollback(self):
            events.append("rollback")

        def close(self):
            events.append("close")

    monkeypatch.setattr(database, "SessionLocal", FakeSession)
    dependency = database.get_db()
    next(dependency)
    with pytest.raises(RuntimeError, match="request failed"):
        dependency.throw(RuntimeError("request failed"))
    assert events == ["rollback", "close"]


def test_production_requires_explicit_psycopg_driver():
    common = {
        "APP_ENV": "prod",
        "SECRET_KEY": "production-secret-key-with-at-least-32-characters",
        "AUTH_ADMIN_PASSWORD": "configured-outside-source-control",
    }
    invalid = Settings(DATABASE_URL="postgresql://user:pass@db/app", **common)
    valid = Settings(DATABASE_URL="postgresql+psycopg://user:pass@db/app", **common)

    assert any("psycopg driver" in error for error in invalid.validate_startup())
    assert not any("psycopg driver" in error for error in valid.validate_startup())
