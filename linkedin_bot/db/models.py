"""SQLAlchemy 2.0 database models for application tracking.

Uses Mapped types for full type safety and the ApplicationStatus
StrEnum for type-safe status values.
"""

from datetime import UTC, datetime
from typing import ClassVar

from sqlalchemy import DateTime, Integer, String, Text, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from linkedin_bot.enums import ApplicationStatus


class Base(DeclarativeBase):
    """SQLAlchemy declarative base."""

    type_annotation_map: ClassVar[dict] = {}  # type: ignore[type-arg]


class ApplicationRecord(Base):
    """Record of an attempted job application.

    Attributes:
        id: Auto-increment primary key.
        job_id: LinkedIn unique job ID (UNIQUE, indexed).
        title: Job title.
        company: Company name.
        location: Job location.
        url: Job listing URL.
        match_score: AI match score (0-100).
        status: Application status (applied/dry_run/skipped/error).
        reason: Reason for skip/error (default empty).
        timestamp: UTC timestamp of the record.
    """

    __tablename__ = "applications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(256), default="")
    company: Mapped[str] = mapped_column(String(256), default="")
    location: Mapped[str] = mapped_column(String(128), default="")
    url: Mapped[str] = mapped_column(Text, default="")
    match_score: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(
        String(32), index=True, default=ApplicationStatus.SKIPPED.value,
    )
    reason: Mapped[str] = mapped_column(Text, default="")
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        default=lambda: datetime.now(UTC),
    )
