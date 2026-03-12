"""Application tracking via database.

Uses typed ApplicationStatus enum and includes skipped jobs
in the deduplication set to avoid wasting AI tokens.
"""

from linkedin_bot.db.repository import ApplicationRepository
from linkedin_bot.enums import ApplicationStatus
from linkedin_bot.logger import get_logger

log = get_logger("tracker")


class ApplicationTracker:
    """Tracks all job applications using the database repository.

    Maintains deduplication by job_id to avoid re-applying.
    """

    def __init__(self) -> None:
        """Initialize tracker. DB must be loaded explicitly via init()."""
        self.applied_job_ids: set[str] = set()

    async def init(self) -> None:
        """Load previously applied job IDs from database to avoid duplicates."""
        try:
            self.applied_job_ids = await ApplicationRepository.get_applied_job_ids()
            log.info("tracker_loaded", existing=len(self.applied_job_ids))
        except Exception as exc:
            log.error("tracker_load_error", error=str(exc))
            raise

    def already_applied(self, job_id: str) -> bool:
        """Check if a job has already been applied to.

        Args:
            job_id: LinkedIn job ID.

        Returns:
            True if already applied or previously skipped.
        """
        return job_id in self.applied_job_ids

    async def record(
        self,
        job_id: str,
        title: str,
        company: str,
        location: str,
        url: str,
        match_score: int,
        status: ApplicationStatus,
        reason: str = "",
    ) -> None:
        """Record a job application attempt.

        Args:
            job_id: LinkedIn job ID.
            title: Job title.
            company: Company name.
            location: Job location.
            url: Job URL.
            match_score: AI match score (0-100).
            status: Application status enum.
            reason: Reason if skipped or errored.
        """
        await ApplicationRepository.add_record(
            job_id=job_id,
            title=title,
            company=company,
            location=location,
            url=url,
            match_score=match_score,
            status=status,
            reason=reason,
        )

        # Add to dedup set for applied, dry_run, and skipped
        if status in (
            ApplicationStatus.APPLIED,
            ApplicationStatus.DRY_RUN,
            ApplicationStatus.SKIPPED,
        ):
            self.applied_job_ids.add(job_id)

        log.info(
            "application_recorded",
            title=title,
            company=company,
            status=status.value,
            match_score=match_score,
        )

    async def get_stats(self) -> dict[str, int]:
        """Get summary statistics of all applications from the database.

        Returns:
            Dictionary with counts by status.
        """
        return await ApplicationRepository.get_stats()
