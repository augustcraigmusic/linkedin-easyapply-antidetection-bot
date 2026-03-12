"""Repository pattern for application record persistence.

Provides UPSERT, deduplication, and aggregated statistics.
Uses the ApplicationStatus StrEnum for type-safe status values.
"""

from sqlalchemy import func, select, update

from linkedin_bot.db.models import ApplicationRecord
from linkedin_bot.db.session import get_db_session
from linkedin_bot.enums import ApplicationStatus
from linkedin_bot.logger import get_logger

log = get_logger(__name__)


class ApplicationRepository:
    """Static repository for application record CRUD operations.

    All methods use the DatabaseManager session factory.
    """

    @staticmethod
    async def add_record(
        *,
        job_id: str,
        title: str,
        company: str,
        location: str,
        url: str,
        match_score: int,
        status: ApplicationStatus,
        reason: str = "",
    ) -> None:
        """Add a new application record or update existing.

        Uses UPSERT: if job_id already exists, updates status and reason.

        Args:
            job_id: LinkedIn unique job ID.
            title: Job title.
            company: Company name.
            location: Job location.
            url: Job listing URL.
            match_score: AI match score (0-100).
            status: Application status enum.
            reason: Reason for skip/error.
        """
        async with get_db_session() as session:
            # Check for existing record (UPSERT)
            stmt = select(ApplicationRecord).where(ApplicationRecord.job_id == job_id)
            result = await session.execute(stmt)
            existing = result.scalar_one_or_none()

            if existing:
                update_stmt = (
                    update(ApplicationRecord)
                    .where(ApplicationRecord.job_id == job_id)
                    .values(status=status.value, reason=reason)
                )
                await session.execute(update_stmt)
                log.debug("record_updated", job_id=job_id, status=status.value)
            else:
                record = ApplicationRecord(
                    job_id=job_id,
                    title=title,
                    company=company,
                    location=location,
                    url=url,
                    match_score=match_score,
                    status=status.value,
                    reason=reason,
                )
                session.add(record)
                log.debug("record_added", job_id=job_id, status=status.value)

    @staticmethod
    async def get_applied_job_ids() -> set[str]:
        """Get all job IDs that have been applied to, dry-run, or skipped.

        Including skipped jobs prevents re-evaluating them every session
        (fixes B6 — token waste on re-evaluation).

        Returns:
            Set of job IDs.
        """
        async with get_db_session() as session:
            stmt = select(ApplicationRecord.job_id).where(
                ApplicationRecord.status.in_([
                    ApplicationStatus.APPLIED.value,
                    ApplicationStatus.DRY_RUN.value,
                    ApplicationStatus.SKIPPED.value,
                ])
            )
            result = await session.execute(stmt)
            return {row[0] for row in result}

    @staticmethod
    async def get_stats() -> dict[str, int]:
        """Get aggregated application statistics by status.

        Returns:
            Dict mapping status names to counts.
        """
        async with get_db_session() as session:
            stmt = (
                select(
                    ApplicationRecord.status,
                    func.count(ApplicationRecord.id),
                )
                .group_by(ApplicationRecord.status)
            )
            result = await session.execute(stmt)
            return {row[0]: row[1] for row in result}
