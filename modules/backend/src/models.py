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
    """Persistent local identity used by authentication and ownership."""

    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint("username", name="uq_users_username"),
        UniqueConstraint("email", name="uq_users_email"),
    )

    id = Column(Integer, primary_key=True)
    username = Column(String(50), nullable=False)
    email = Column(String(255), nullable=False)
    hashed_password = Column(String(255), nullable=False)
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


class TranscriptionOwnership(Base):
    """One persistent user owns one transcription.

    ``owner_sub`` is retained as an explicit legacy bridge. New records always
    populate ``user_id``; unresolved historical rows remain visible for a safe,
    exact username reconciliation instead of being assigned by fallback.
    """

    __tablename__ = "transcription_owners"
    __table_args__ = (
        UniqueConstraint("transcription_id", name="uq_transcription_owners_transcription_id"),
        Index("ix_transcription_owners_owner_sub", "owner_sub"),
        Index("ix_transcription_owners_user_id", "user_id"),
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
    status = Column(String(20), nullable=False, default="open", server_default=text("'open'"))
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())
    meeting = relationship("Meeting", back_populates="action_items")

    def to_dict(self):
        return {
            "id": self.id, "meeting_id": self.meeting_id,
            "description": self.description, "assignee": self.assignee,
            "due_date": self.due_date.isoformat() if self.due_date else None,
            "status": self.status,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "source": "manual",
        }


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
