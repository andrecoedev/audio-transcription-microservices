import os

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker


@pytest.fixture(scope="session")
def postgres_engine():
    url = os.getenv("P2A_TEST_DATABASE_URL")
    if not url:
        pytest.skip("P2A_TEST_DATABASE_URL is required for PostgreSQL integration tests")
    if make_url(url).get_backend_name() != "postgresql":
        pytest.fail("P2A_TEST_DATABASE_URL must point to PostgreSQL")
    engine = create_engine(url, pool_pre_ping=True, pool_size=5, max_overflow=0)
    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))
    yield engine
    engine.dispose()


@pytest.fixture
def postgres_session_factory(postgres_engine):
    with postgres_engine.begin() as connection:
        connection.execute(
            text(
                "TRUNCATE audit_events, transcription_jobs, transcription_owners, "
                "transcriptions, users RESTART IDENTITY CASCADE"
            )
        )
    factory = sessionmaker(autocommit=False, autoflush=False, bind=postgres_engine)
    yield factory
    with postgres_engine.begin() as connection:
        connection.execute(
            text(
                "TRUNCATE audit_events, transcription_jobs, transcription_owners, "
                "transcriptions, users RESTART IDENTITY CASCADE"
            )
        )
