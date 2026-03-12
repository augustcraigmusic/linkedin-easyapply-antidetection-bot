"""Main entry point — LinkedIn Auto-Apply Bot orchestrator.

CC reduced from 34 to ≤10 by extracting:
- _validate_config, _filter_listings, _score_and_apply, _process_search_page
- _search_keyword_location, _run_session
"""

import asyncio
import sys
from typing import Any

from playwright.async_api import BrowserContext, Page
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from linkedin_bot.ai_engine import AIEngine
from linkedin_bot.applicator import click_easy_apply, navigate_and_submit
from linkedin_bot.browser import (
    create_browser_session,
    human_delay,
    save_session,
)
from linkedin_bot.config import SearchConfig, load_resume, load_search_config, settings
from linkedin_bot.db.session import init_db
from linkedin_bot.enums import ApplicationStatus
from linkedin_bot.exceptions import BrowserDeadError
from linkedin_bot.job_search import (
    JobListing,
    build_search_url,
    get_job_listings,
    should_skip_job,
)
from linkedin_bot.linkedin_auth import login
from linkedin_bot.logger import get_logger, setup_logging
from linkedin_bot.tracker import ApplicationTracker

log = get_logger("main")
console = Console()


def format_resume_as_text(resume_data: dict[str, Any]) -> str:
    """Convert structured resume YAML to plain text for AI prompts.

    Args:
        resume_data: Parsed resume.yaml dictionary.

    Returns:
        Flat text representation of the resume.
    """
    parts: list[str] = []

    personal = resume_data.get("personal", {})
    parts.append(f"Name: {personal.get('name', 'N/A')}")
    parts.append(f"Location: {personal.get('location', 'N/A')}")
    parts.append(f"Experience: {personal.get('years_of_experience', 'N/A')} years")
    parts.append("")
    parts.append(f"Summary: {resume_data.get('summary', '')}")
    parts.append("")

    skills = resume_data.get("skills", {})
    for category, skill_list in skills.items():
        if isinstance(skill_list, list):
            parts.append(f"{category}: {', '.join(str(s) for s in skill_list)}")
    parts.append("")

    for exp in resume_data.get("experience", []):
        parts.append(
            f"{exp.get('title', '')} at {exp.get('company', '')} ({exp.get('period', '')})"
        )
        for highlight in exp.get("highlights", []):
            parts.append(f"  - {highlight}")
        parts.append("")

    return "\n".join(parts)


def print_banner(search_config: SearchConfig) -> None:
    """Print the startup banner with configuration summary."""
    mode_color = "yellow" if settings.dry_run else "green"
    mode_text = "DRY RUN" if settings.dry_run else "LIVE"
    resume_name = settings.resume_path.split("/")[-1] if settings.resume_path else "Not set"
    resume_status = f"✅ {resume_name}" if settings.resume_path else "⚠ Not set"

    console.print(
        Panel(
            f"[bold cyan]LinkedIn Auto-Apply Bot[/]\n"
            f"[dim]DeepSeek AI · Playwright · v2.0.0[/]\n\n"
            f"Mode: [bold {mode_color}]{mode_text}[/]\n"
            f"Applications: [bold]{settings.max_applications_per_session}[/]\n"
            f"Keywords: [bold]{', '.join(search_config.keywords)}[/]\n"
            f"Delay: [bold]{settings.min_delay_seconds}-{settings.max_delay_seconds}s[/]\n"
            f"Resume: [bold]{resume_status}[/]",
            border_style="cyan",
            title="🚀 Starting Up",
        )
    )


async def print_stats(tracker: ApplicationTracker) -> None:
    """Print application statistics summary."""
    raw_stats = await tracker.get_stats()
    # Map enum values to friendly keys, with defaults for missing statuses
    applied = raw_stats.get(ApplicationStatus.APPLIED.value, 0)
    dry_run = raw_stats.get(ApplicationStatus.DRY_RUN.value, 0)
    skipped = raw_stats.get(ApplicationStatus.SKIPPED.value, 0)
    errors = raw_stats.get(ApplicationStatus.ERROR.value, 0)
    total = applied + dry_run + skipped + errors

    table = Table(title="📊 Session Summary", border_style="cyan")
    table.add_column("Status", style="bold")
    table.add_column("Count", justify="right")
    table.add_row("✅ Applied", str(applied))
    table.add_row("🔍 Dry Run", str(dry_run))
    table.add_row("⏭  Skipped", str(skipped))
    table.add_row("❌ Errors", str(errors))
    table.add_row("📋 Total", str(total), style="bold cyan")
    console.print(table)


def _validate_config() -> bool:
    """Validate required configuration is present.

    Returns:
        True if all required settings are configured.
    """
    if not settings.deepseek_api_key.get_secret_value():
        console.print("[bold red]❌ DEEPSEEK_API_KEY not set in .env[/]")
        return False

    if not settings.linkedin_email or not settings.linkedin_password.get_secret_value():
        console.print("[bold red]❌ LinkedIn credentials not set in .env[/]")
        return False

    return True


async def _record_skip(
    tracker: ApplicationTracker,
    listing: JobListing,
    match_score: int,
    reason: str,
) -> None:
    """Record a skipped job in the tracker."""
    await tracker.record(
        job_id=listing.job_id,
        title=listing.title,
        company=listing.company,
        location=listing.location,
        url=listing.url,
        match_score=match_score,
        status=ApplicationStatus.SKIPPED,
        reason=reason,
    )


async def process_job_application(
    page: Page,
    listing: JobListing,
    match_score: int,
    ai: AIEngine,
    tracker: ApplicationTracker,
    default_answers: dict[str, str],
) -> bool:
    """Process a single job application (after filtering and scoring).

    Args:
        page: Playwright page instance.
        listing: The job listing to process.
        match_score: The pre-calculated AI match score.
        ai: AI engine instance.
        tracker: Application tracker.
        default_answers: Default form answers.

    Returns:
        True if application was submitted (or dry_run).
    """
    direct_url = f"https://www.linkedin.com/jobs/view/{listing.job_id}/"

    if listing.job_id:
        try:
            await page.goto(direct_url, wait_until="domcontentloaded", timeout=15_000)
            await human_delay(2.0, 3.5)
        except Exception as nav_err:
            err_msg = str(nav_err)
            log.warning("job_navigation_error", title=listing.title[:30], error=err_msg)
            await tracker.record(
                job_id=listing.job_id,
                title=listing.title,
                company=listing.company,
                location=listing.location,
                url=direct_url,
                match_score=match_score,
                status=ApplicationStatus.ERROR,
                reason="Failed to navigate to job page",
            )
            if "closed" in err_msg.lower():
                raise BrowserDeadError("Browser connection lost") from nav_err
            return False

    if not await click_easy_apply(page):
        await tracker.record(
            job_id=listing.job_id,
            title=listing.title,
            company=listing.company,
            location=listing.location,
            url=listing.url,
            match_score=match_score,
            status=ApplicationStatus.ERROR,
            reason="Easy Apply button not found",
        )
        return False

    success = await navigate_and_submit(
        page=page,
        listing=listing,
        ai=ai,
        default_answers=default_answers,
        dry_run=settings.dry_run,
    )

    status = (
        ApplicationStatus.DRY_RUN if settings.dry_run
        else ApplicationStatus.APPLIED if success
        else ApplicationStatus.ERROR
    )
    await tracker.record(
        job_id=listing.job_id,
        title=listing.title,
        company=listing.company,
        location=listing.location,
        url=listing.url,
        match_score=match_score,
        status=status,
        reason="" if success else "Form submission failed",
    )
    return success


async def _filter_listings(
    listings: list[JobListing],
    tracker: ApplicationTracker,
    search_config: SearchConfig,
) -> list[JobListing]:
    """Filter job listings by tracker history and blacklists.

    Args:
        listings: Raw job listings from the search page.
        tracker: Application tracker for dedup.
        search_config: Search configuration with blacklists.

    Returns:
        Filtered list of valid listings.
    """
    valid: list[JobListing] = []
    for listing in listings:
        if tracker.already_applied(listing.job_id):
            log.info("skipping_duplicate", title=listing.title[:40])
            continue

        skip, reason = should_skip_job(
            listing,
            search_config.blacklist_titles,
            search_config.blacklist_companies,
        )
        if skip:
            await _record_skip(tracker, listing, 0, reason)
            console.print(f"  ⏭  [dim]{listing.title[:35]}[/] — {reason}")
            continue

        valid.append(listing)

    return valid


async def _score_and_apply(
    page: Page,
    valid_listings: list[JobListing],
    ai: AIEngine,
    tracker: ApplicationTracker,
    default_answers: dict[str, str],
    min_score: int,
    total_applied: int,
) -> tuple[int, bool]:
    """Score listings in bulk and process applications.

    Args:
        page: Playwright page instance.
        valid_listings: Pre-filtered job listings.
        ai: AI engine instance.
        tracker: Application tracker.
        default_answers: Default form answers.
        min_score: Minimum match score threshold.
        total_applied: Running count of applications.

    Returns:
        Tuple of (updated total_applied, browser_alive).
    """
    console.print(f"  [cyan]🧠 Bulk scoring {len(valid_listings)} jobs...[/]")
    bulk_input = [
        {"title": lst.title, "description": lst.description}
        for lst in valid_listings
    ]
    scores = await ai.calculate_match_scores_bulk(bulk_input)

    for listing, match_score in zip(valid_listings, scores, strict=True):
        if total_applied >= settings.max_applications_per_session:
            console.print(
                f"\n[yellow]⚠ Session limit ({settings.max_applications_per_session})[/]"
            )
            break

        score_color = "green" if match_score >= min_score else "red"
        console.print(
            f"  📋 [bold]{listing.title[:38]}[/] @ "
            f"[cyan]{listing.company}[/] "
            f"— Score: [{score_color}]{match_score}%[/]"
        )

        if match_score < min_score:
            await _record_skip(
                tracker, listing, match_score,
                f"Low match ({match_score}% < {min_score}%)",
            )
            continue

        try:
            success = await process_job_application(
                page=page,
                listing=listing,
                match_score=match_score,
                ai=ai,
                tracker=tracker,
                default_answers=default_answers,
            )
            if success:
                total_applied += 1
        except BrowserDeadError:
            console.print("  [red]⚠ Browser closed, ending session[/]")
            return total_applied, False
        except Exception as job_err:
            log.warning(
                "job_processing_error",
                title=listing.title[:40],
                error=str(job_err),
            )
            continue

        await human_delay()

    return total_applied, True


async def _process_search_page(
    page: Page,
    keyword: str,
    location: str,
    page_num: int,
    search_config: SearchConfig,
    ai: AIEngine,
    tracker: ApplicationTracker,
    default_answers: dict[str, str],
    total_applied: int,
) -> tuple[int, bool, bool]:
    """Process a single search results page.

    Args:
        page: Playwright page instance.
        keyword: Search keyword.
        location: Search location.
        page_num: Zero-based page number.
        search_config: Search configuration.
        ai: AI engine instance.
        tracker: Application tracker.
        default_answers: Default form answers.
        total_applied: Running count of applications.

    Returns:
        Tuple of (updated total_applied, browser_alive, has_more_pages).
    """
    start = page_num * 25

    search_url = build_search_url(
        keyword=keyword,
        location=location,
        remote_only=search_config.remote_only,
        experience_levels=search_config.experience_levels,
        date_posted=search_config.date_posted,
        start=start,
    )

    if page_num > 0:
        console.print(f"  [dim]Page {page_num + 1}...[/]")

    try:
        await page.goto(search_url, wait_until="domcontentloaded", timeout=30_000)
        await human_delay(3.0, 5.0)
    except Exception as nav_err:
        err_msg = str(nav_err)
        log.warning("search_navigation_error", keyword=keyword, error=err_msg)
        if "closed" in err_msg.lower():
            return total_applied, False, False
        return total_applied, True, False

    listings = await get_job_listings(page)
    if not listings:
        if page_num == 0:
            console.print("  [dim]No jobs found[/]")
        return total_applied, True, False

    if page_num == 0:
        console.print(f"  [dim]Found {len(listings)} jobs[/]\n")

    valid_listings = await _filter_listings(listings, tracker, search_config)
    if not valid_listings:
        return total_applied, True, True

    min_score = search_config.min_match_score
    total_applied, browser_alive = await _score_and_apply(
        page, valid_listings, ai, tracker, default_answers, min_score, total_applied,
    )

    return total_applied, browser_alive, True


async def _run_session(
    page: Page,
    context: BrowserContext,
    search_config: SearchConfig,
    ai: AIEngine,
    tracker: ApplicationTracker,
    default_answers: dict[str, str],
) -> None:
    """Run the main bot session (login + search loop).

    Args:
        page: Playwright page instance.
        context: Browser context for session saving.
        search_config: Search configuration.
        ai: AI engine instance.
        tracker: Application tracker.
        default_answers: Default form answers.
    """
    console.print("\n[bold]🔐 Logging into LinkedIn...[/]")
    if not await login(page, context):
        console.print("[bold red]❌ Login failed. Check credentials in .env[/]")
        return

    console.print("[bold green]✅ Logged in successfully![/]\n")

    total_applied = 0
    keywords = search_config.keywords
    locations = search_config.locations
    max_pages = settings.max_pages_per_search

    for keyword in keywords:
        if total_applied >= settings.max_applications_per_session:
            break

        for location in locations:
            if total_applied >= settings.max_applications_per_session:
                break

            console.print(
                f"\n[bold cyan]🔍 Searching:[/] '{keyword}'"
                f"{f' in {location}' if location else ''}"
            )

            for page_num in range(max_pages):
                if total_applied >= settings.max_applications_per_session:
                    break

                total_applied, browser_alive, has_more = await _process_search_page(
                    page, keyword, location, page_num, search_config,
                    ai, tracker, default_answers, total_applied,
                )

                if not browser_alive:
                    await save_session(context)
                    await print_stats(tracker)
                    return

                if not has_more:
                    break

    await save_session(context)
    console.print()
    await print_stats(tracker)


async def main() -> None:
    """Main bot orchestration loop with pagination support."""
    setup_logging()
    await init_db()
    search_config = load_search_config()
    print_banner(search_config)

    if not _validate_config():
        return

    resume_data = load_resume()
    resume_text = format_resume_as_text(resume_data)
    default_answers = resume_data.get("default_answers", {})

    ai = AIEngine(resume_text)
    tracker = ApplicationTracker()
    await tracker.init()

    async with create_browser_session() as session:
        try:
            await _run_session(
                session.page, session.context, search_config,
                ai, tracker, default_answers,
            )
        except KeyboardInterrupt:
            console.print("\n[bold yellow]⚠ Interrupted by user[/]")
            await save_session(session.context)
            await print_stats(tracker)


def run() -> None:
    """Synchronous entry point."""
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        console.print("\n[dim]Goodbye! 👋[/]")
        sys.exit(0)


if __name__ == "__main__":
    run()
