"""Unit coverage for Firebase identity ownership constraints."""
import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from src.models import Base, FirebaseIdentity, User
from src.security import verify_password


def test_firebase_identity_constraints_and_passwordless_users():
    engine = create_engine("sqlite://")

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(connection, _record):
        connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    try:
        with Session(engine) as db:
            existing = User(
                username="existing", email="existing@example.test", hashed_password="old-hash"
            )
            federated = User(
                username="federated", email="federated@example.test", hashed_password=None
            )
            db.add_all([existing, federated])
            db.flush()
            db.add(FirebaseIdentity(project_id="firebase-project", uid="firebase-uid", user_id=federated.id))
            db.commit()

            db.add(FirebaseIdentity(project_id="firebase-project", uid="firebase-uid", user_id=existing.id))
            with pytest.raises(IntegrityError):
                db.commit()
            db.rollback()

            db.add(FirebaseIdentity(project_id="another-project", uid="another-uid", user_id=federated.id))
            with pytest.raises(IntegrityError):
                db.commit()
            db.rollback()

            assert db.get(User, existing.id).hashed_password == "old-hash"
            assert db.get(User, federated.id).hashed_password is None
            assert not verify_password('synthetic-password', federated.hashed_password)
    finally:
        Base.metadata.drop_all(engine)
        engine.dispose()
