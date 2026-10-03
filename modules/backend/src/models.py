"""SQLAlchemy models for the durable application state.

PostgreSQL is the official runtime database. The JSON variant keeps isolated
unit tests usable with SQLite without making it a second production runtime.
"""

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Column,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import declarative_base, relationship
from sqlalchemy.sql import func

Base = declarative_base()

TRANSCRIPTION_STATUSES = ("queued", "processing", "completed", "failed")
JOB_STATUSES = ("queued", "processing", "completed", "failed")


class Transcription(Base):
    """Uploaded audio metadata and the current transcription result."""

    __tablename__ = "transcriptions"
    __table_args__ = (
        CheckConstraint("file_size_mb >= 0", name="ck_transcriptions_file_size_nonnegative"),
        CheckConstraint(
            "duration_seconds >= 0", name="ck_transcriptions_duration_nonnegative"
        ),
        CheckConstraint(
            "processing_time_seconds IS NULL OR processing_time_seconds >= 0",
            name="ck_transcriptions_processing_time_nonnegative",
        ),
        CheckConstraint(
            "num_speakers IS NULL OR num_speakers >= 0",
            name="ck_transcriptions_num_speakers_nonnegative",
        ),
        CheckConstraint(
            "word_count IS NULL OR word_count >= 0",
            name="ck_transcriptions_word_count_nonnegative",
        ),
        CheckConstraint(
            "status IN ('queued', 'processing', 'completed', 'failed')",
            name="ck_transcriptions_status",
        ),
        Index("ix_transcriptions_status_created_at", "status", "created_at"),
    )

    id = Column(Integer, primary_key=True)
    filename = Column(String(255), nullable=False)
    original_filename = Column(String(255), nullable=False)
    file_size_mb = Column(Float, nullable=False)
    duration_seconds = Column(Float, nullable=False)
    transcription_model = Column(String(50), nullable=False)
    use_diarization = Column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    segments = Column(
        JSON().with_variant(JSONB, "postgresql"), nullable=False, default=list
    )
    num_speakers = Column(Integer, nullable=True)
    word_count = Column(Integer, nullable=True)
    processing_time_seconds = Column(Float, nullable=True)
    status = Column(
        String(20), nullable=False, default="queued", server_default=text("'queued'")
    )
    error_message = Column(Text, nullable=True)
    created_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    ownership = relationship(
        "TranscriptionOwnership",
        back_populates="transcription",
        uselist=False,
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    job = relationship(
        "TranscriptionJob",
        back_populates="transcription",
        uselist=False,
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    meeting = relationship(
        "Meeting",
        back_populates="transcription",
        uselist=False,
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    def __repr__(self):
        return f"<Transcription(id={self.id}, filename={self.filename}, status={self.status})>"

    def to_dict(self):
        return {
            "id": self.id,
            "filename": self.filename,
            "original_filename": self.original_filename,
            "file_size_mb": self.file_size_mb,
            "duration_seconds": self.duration_seconds,
            "transcription_model": self.transcription_model,
            "use_diarization": self.use_diarization,
            "segments": self.segments,
            "num_speakers": self.num_speakers,
            "word_count": self.word_count,
            "processing_time_seconds": self.processing_time_seconds,
            "status": self.status,
            "error_message": self.error_message,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class User(Base):
    """Persistent application identity used by authentication and ownership."""

    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint("username", name="uq_users_username"),
        UniqueConstraint("email", name="uq_users_email"),
        CheckConstraint("registration_source IN ('local', 'public')", name="ck_users_registration_source"),
    )

    id = Column(Integer, primary_key=True)
    username = Column(String(50), nullable=False)
    email = Column(String(255), nullable=False)
    hashed_password = Column(String(255), nullable=True)
    registration_source = Column(String(16), nullable=False, default="local", server_default=text("'local'"))
    is_active = Column(Boolean, nullable=False, default=True, server_default=text("true"))
    is_superuser = Column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    created_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
    ownerships = relationship("TranscriptionOwnership", back_populates="user")
    audit_events = relationship(
        "AuditEvent",
        back_populates="actor_user",
        passive_deletes=True,
    )

    def __repr__(self):
        return f"<User(id={self.id}, username={self.username})>"


class FirebaseIdentity(Base):
    """Firebase identity bound to one internal user."""

    __tablename__ = "firebase_identities"
    __table_args__ = (
        UniqueConstraint("user_id", name="uq_firebase_identity_user"),
    )

    project_id = Column(String(128), primary_key=True)
    uid = Column(String(128), primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    created_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class UserProviderPreferences(Base):
    __tablename__ = "user_provider_preferences"
    __table_args__ = (
        CheckConstraint("transcription_provider IN ('automatic', 'whisper', 'assemblyai')", name="ck_preferences_transcription"),
        CheckConstraint("intelligence_provider IN ('automatic', 'gemini')", name="ck_preferences_intelligence"),
    )
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    transcription_provider = Column(String(32), nullable=False, default="automatic", server_default="automatic")
    intelligence_provider = Column(String(32), nullable=False, default="automatic", server_default="automatic")
    use_diarization = Column(Boolean, nullable=False, default=False, server_default=text("false"))


class UserProviderCredential(Base):
    """Authenticated ciphertext only; replacement creates a new immutable ID."""
    __tablename__ = "user_provider_credentials"
    __table_args__ = (
        UniqueConstraint("user_id", "provider", name="uq_user_provider_credential"),
        CheckConstraint("provider IN ('assemblyai', 'gemini')", name="ck_user_provider_credential_provider"),
    )
    id = Column(String(36), primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    provider = Column(String(32), nullable=False)
    ciphertext = Column(Text, nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())


class GuestSession(Base):
    """Expiring server-side identity, not an account or a provider credential."""
    __tablename__ = "guest_sessions"
    __table_args__ = (CheckConstraint("jobs_created >= 0", name="ck_guest_sessions_jobs_created"),)

    id = Column(String(36), primary_key=True)
    expires_at = Column(DateTime(timezone=True), nullable=False, index=True)
    jobs_created = Column(Integer, nullable=False, default=0, server_default=text("0"))
    claimed_by_user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())


class TranscriptionOwnership(Base):
    """One persistent user or temporary guest owns one transcription.

    ``owner_sub`` is retained as an explicit legacy bridge. New account records
    populate ``user_id``; Guest records use ``guest_session_id`` instead.
    Unresolved historical rows remain visible for a safe,
    exact username reconciliation instead of being assigned by fallback.
    """

    __tablename__ = "transcription_owners"
    __table_args__ = (
        UniqueConstraint("transcription_id", name="uq_transcription_owners_transcription_id"),
        Index("ix_transcription_owners_owner_sub", "owner_sub"),
        Index("ix_transcription_owners_user_id", "user_id"),
        CheckConstraint("guest_session_id IS NULL OR user_id IS NULL", name="ck_transcription_owners_single_context"),
    )

    id = Column(Integer, primary_key=True)
    transcription_id = Column(
        Integer,
        ForeignKey("transcriptions.id", ondelete="CASCADE"),
        nullable=False,
    )
    owner_sub = Column(String(255), nullable=False)
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=True,
    )
    guest_session_id = Column(String(36), ForeignKey("guest_sessions.id", ondelete="RESTRICT"), nullable=True, index=True)
    created_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    transcription = relationship("Transcription", back_populates="ownership")
    user = relationship("User", back_populates="ownerships")

    def __repr__(self):
        return (
            f"<TranscriptionOwnership(transcription_id={self.transcription_id}, "
            f"user_id={self.user_id}, owner_sub={self.owner_sub})>"
        )


class TranscriptionJob(Base):
    """Current asynchronous execution state for one transcription."""

    __tablename__ = "transcription_jobs"
    __table_args__ = (
        UniqueConstraint("transcription_id", name="uq_transcription_jobs_transcription_id"),
        CheckConstraint(
            "status IN ('queued', 'processing', 'completed', 'failed')",
            name="ck_transcription_jobs_status",
        ),
        Index("ix_transcription_jobs_status_created_at", "status", "created_at"),
    )

    id = Column(Integer, primary_key=True)
    transcription_id = Column(
        Integer,
        ForeignKey("transcriptions.id", ondelete="CASCADE"),
        nullable=False,
    )
    input_path = Column(String(500), nullable=False)
    max_duration_seconds = Column(Integer, nullable=True)
    timeout_seconds = Column(Integer, nullable=True)
    credential_source = Column(String(16), nullable=False, default="platform", server_default="platform")
    credential_id = Column(String(36), ForeignKey("user_provider_credentials.id", ondelete="SET NULL"), nullable=True)
    credential_user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    provider_attempted_at = Column(DateTime(timezone=True), nullable=True)
    use_diarization = Column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    transcription_model = Column(String(50), nullable=False)
    status = Column(
        String(20), nullable=False, default="queued", server_default=text("'queued'")
    )
    error_message = Column(Text, nullable=True)
    created_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    failed_at = Column(DateTime(timezone=True), nullable=True)
    transcription = relationship("Transcription", back_populates="job")

    def __repr__(self):
        return (
            f"<TranscriptionJob(transcription_id={self.transcription_id}, "
            f"status={self.status})>"
        )


class PlatformProviderBudget(Base):
    """Cumulative spending ceiling; deletion/restart never replenishes it."""

    __tablename__ = "platform_provider_budgets"
    __table_args__ = (
        CheckConstraint("limit_cents >= 0 AND reserved_cents >= 0 AND reserved_cents <= limit_cents",
                        name="ck_platform_provider_budget_amounts"),
    )
    provider = Column(String(32), primary_key=True)
    limit_cents = Column(Integer, nullable=False)
    reserved_cents = Column(Integer, nullable=False, default=0, server_default="0")


class PlatformProviderCall(Base):
    """Immutable platform provenance and no-repeat guard, retained after deletion."""

    __tablename__ = "platform_provider_calls"
    __table_args__ = (
        CheckConstraint("reserved_cents > 0", name="ck_platform_provider_call_amount"),
        CheckConstraint("context IN ('guest', 'local')", name="ck_platform_provider_call_context"),
        CheckConstraint("state IN ('reserved', 'attempted')", name="ck_platform_provider_call_state"),
    )
    id = Column(Integer, primary_key=True)
    transcription_id = Column(Integer, ForeignKey("transcriptions.id", ondelete="SET NULL"), unique=True)
    provider = Column(String(32), ForeignKey("platform_provider_budgets.provider", ondelete="RESTRICT"), nullable=False)
    context = Column(String(16), nullable=False)
    credential_source = Column(String(16), nullable=False, default="platform", server_default="platform")
    reserved_cents = Column(Integer, nullable=False)
    state = Column(String(16), nullable=False, default="reserved", server_default="reserved")
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())


class Meeting(Base):
    """Product metadata for a completed transcription; content stays in JSONB."""

    __tablename__ = "meetings"

    id = Column(
        Integer,
        ForeignKey("transcriptions.id", ondelete="CASCADE"),
        primary_key=True,
    )
    title = Column(String(255), nullable=False)
    language = Column(String(16), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
    transcription = relationship("Transcription", back_populates="meeting")
    intelligence_revisions = relationship(
        "MeetingIntelligence", back_populates="meeting",
        cascade="all, delete-orphan", passive_deletes=True,
    )
    speakers = relationship(
        "MeetingSpeaker",
        back_populates="meeting",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    action_items = relationship(
        "MeetingActionItem", back_populates="meeting",
        cascade="all, delete-orphan", passive_deletes=True,
    )


class MeetingActionItem(Base):
    """User-managed actions; editing them never updates an AI revision."""

    __tablename__ = "meeting_action_items"
    __table_args__ = (
        CheckConstraint("status IN ('open', 'done', 'dismissed')", name="ck_meeting_action_items_status"),
        CheckConstraint("length(trim(description)) > 0", name="ck_meeting_action_items_description"),
        Index("ix_meeting_action_items_meeting_id", "meeting_id"),
    )

    id = Column(Integer, primary_key=True)
    meeting_id = Column(Integer, ForeignKey("meetings.id", ondelete="CASCADE"), nullable=False)
    description = Column(String(4000), nullable=False)
    assignee = Column(String(255), nullable=True)
    due_date = Column(Date, nullable=True)
    source_intelligence_id = Column(Integer, ForeignKey("meeting_intelligence.id", ondelete="RESTRICT"), nullable=True)
    source_revision = Column(Integer, nullable=True)
    source_index = Column(Integer, nullable=True)
    original_description = Column(String(4000), nullable=True)
    original_assignee = Column(String(255), nullable=True)
    original_due_date = Column(String(255), nullable=True)
    evidence = Column(JSON().with_variant(JSONB, "postgresql"), nullable=True)
    status = Column(String(20), nullable=False, default="open", server_default=text("'open'"))
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())
    meeting = relationship("Meeting", back_populates="action_items")
    source_intelligence = relationship("MeetingIntelligence")

    def to_dict(self):
        return {
            "id": self.id, "meeting_id": self.meeting_id,
            "description": self.description, "assignee": self.assignee,
            "due_date": self.due_date.isoformat() if self.due_date else None,
            "status": self.status,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "source": "ai_reviewed" if self.source_intelligence_id is not None else "manual",
            "source_revision": self.source_revision,
            "source_index": self.source_index,
            "original_description": self.original_description,
            "original_assignee": self.original_assignee,
            "original_due_date": self.original_due_date,
            "evidence": self.evidence,
        }


class MeetingActionSuggestionReview(Base):
    """Persistent per-suggestion review state, including after action deletion."""

    __tablename__ = "meeting_action_suggestion_reviews"
    __table_args__ = (
        UniqueConstraint("meeting_id", "source_revision", "source_index", name="uq_meeting_action_suggestion_review_source"),
        CheckConstraint("status IN ('accepted', 'dismissed', 'deleted')", name="ck_meeting_action_suggestion_review_status"),
        CheckConstraint("(status = 'accepted' AND action_id IS NOT NULL) OR (status != 'accepted' AND action_id IS NULL)", name="ck_meeting_action_suggestion_review_action"),
        Index("ix_meeting_action_suggestion_reviews_meeting_id", "meeting_id"),
    )

    id = Column(Integer, primary_key=True)
    meeting_id = Column(Integer, ForeignKey("meetings.id", ondelete="CASCADE"), nullable=False)
    source_intelligence_id = Column(Integer, ForeignKey("meeting_intelligence.id", ondelete="RESTRICT"), nullable=False)
    source_revision = Column(Integer, nullable=False)
    source_index = Column(Integer, nullable=False)
    status = Column(String(20), nullable=False)
    action_id = Column(Integer, ForeignKey("meeting_action_items.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())


class MeetingSpeaker(Base):
    """Stable diarization identifier with an optional user-facing name."""

    __tablename__ = "meeting_speakers"

    meeting_id = Column(
        Integer,
        ForeignKey("meetings.id", ondelete="CASCADE"),
        primary_key=True,
    )
    speaker_id = Column(String(100), primary_key=True)
    display_name = Column(String(100), nullable=True)
    meeting = relationship("Meeting", back_populates="speakers")


class MeetingIntelligence(Base):
    __tablename__ = "meeting_intelligence"
    __table_args__ = (
        UniqueConstraint("meeting_id", "revision", name="uq_intelligence_meeting_revision"),
        CheckConstraint("status IN ('pending', 'processing', 'completed', 'failed')", name="ck_intelligence_status"),
        CheckConstraint("revision > 0", name="ck_intelligence_revision"),
        CheckConstraint("status != 'completed' OR result IS NOT NULL", name="ck_intelligence_completed_result"),
        Index("ix_intelligence_one_active", "meeting_id", unique=True,
              postgresql_where=text("status IN ('pending', 'processing')"),
              sqlite_where=text("status IN ('pending', 'processing')")),
    )

    id = Column(Integer, primary_key=True)
    meeting_id = Column(Integer, ForeignKey("meetings.id", ondelete="CASCADE"), nullable=False)
    revision = Column(Integer, nullable=False)
    schema_version = Column(String(16), nullable=False, default="1")
    provider = Column(String(50), nullable=False)
    model = Column(String(100), nullable=False)
    credential_source = Column(String(16), nullable=False, default="platform", server_default="platform")
    credential_id = Column(String(36), ForeignKey("user_provider_credentials.id", ondelete="SET NULL"), nullable=True)
    credential_user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    status = Column(String(20), nullable=False, default="pending")
    result = Column(JSON().with_variant(JSONB, "postgresql"), nullable=True)
    source_metadata = Column(JSON().with_variant(JSONB, "postgresql"), nullable=False)
    input_fingerprint = Column(String(64), nullable=False)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    meeting = relationship("Meeting", back_populates="intelligence_revisions")


class AuditEvent(Base):
    """Minimal append-only application audit event without content payloads."""

    __tablename__ = "audit_events"
    __table_args__ = (
        Index("ix_audit_events_timestamp", "timestamp"),
        Index("ix_audit_events_event_timestamp", "event", "timestamp"),
        Index("ix_audit_events_actor_user_id", "actor_user_id"),
    )

    id = Column(Integer, primary_key=True)
    timestamp = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    actor_user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    actor_type = Column(
        String(20), nullable=False, default="system", server_default=text("'system'")
    )
    event = Column(String(100), nullable=False)
    resource_type = Column(String(50), nullable=True)
    resource_id = Column(String(100), nullable=True)
    event_metadata = Column(
        "metadata",
        JSON().with_variant(JSONB, "postgresql"),
        nullable=False,
        default=dict,
    )

    actor_user = relationship("User", back_populates="audit_events")
