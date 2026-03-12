"""Job search, pagination, and listing extraction from LinkedIn.

Validates job_id extraction with UUID fallback (BUG-MED-2),
reduces CC by extracting helper functions.
"""

import uuid
from dataclasses import dataclass
from urllib.parse import urlencode

from playwright.async_api import ElementHandle, Page

from linkedin_bot.browser import human_delay, scroll_element
from linkedin_bot.logger import get_logger

log = get_logger("job_search")

JOBS_BASE_URL = "https://www.linkedin.com/jobs/search/?"

EXPERIENCE_MAP = {1: "1", 2: "2", 3: "3", 4: "4", 5: "5", 6: "6"}
DATE_POSTED_MAP = {1: "r86400", 2: "r604800", 3: "r2592000"}

# Selectors (multi-fallback for resilience against LinkedIn UI changes)
_JOB_LIST_SELECTORS = [
    ".scaffold-layout__list-container",
    ".jobs-search-results-list",
    '[class*="jobs-search-results"]',
    ".scaffold-layout__list",
    ".scaffold-layout__list-detail-container",
    '[class*="scaffold-layout__list"]',
]

_JOB_CARD_SELECTORS = [
    ".scaffold-layout__list-container li.ember-view",
    "li.ember-view.jobs-search-results__list-item",
    ".job-card-container",
    "[data-occludable-job-id]",
    "li.jobs-search-results__list-item",
    ".scaffold-layout__list-container .artdeco-list__item",
    "li[data-occludable-entity-urn]",
]

_TITLE_SELECTORS = [
    ".job-details-jobs-unified-top-card__job-title",
    ".jobs-unified-top-card__job-title",
    'h1 a[data-tracking-control-name="public_jobs_topcard-title"]',
    ".t-24.job-details-jobs-unified-top-card__job-title",
]

_COMPANY_SELECTORS = [
    ".job-details-jobs-unified-top-card__company-name",
    ".jobs-unified-top-card__company-name",
    ".job-details-jobs-unified-top-card__primary-description-without-tagline a",
]

_DESCRIPTION_SELECTORS = [
    ".jobs-description__content",
    ".jobs-box__html-content",
    "#job-details",
]


@dataclass(frozen=True, slots=True)
class JobListing:
    """Represents a single job listing extracted from LinkedIn."""

    job_id: str
    title: str
    company: str
    location: str
    description: str
    url: str
    is_easy_apply: bool
    already_applied: bool


def build_search_url(
    keyword: str,
    location: str = "",
    remote_only: bool = True,
    experience_levels: list[int] | None = None,
    date_posted: int = 2,
    easy_apply_only: bool = True,
    start: int = 0,
) -> str:
    """Build a LinkedIn jobs search URL with filters.

    Args:
        keyword: Job search keyword.
        location: Location filter.
        remote_only: Filter for remote positions only.
        experience_levels: List of experience level codes.
        date_posted: Date posted filter code (1, 2, or 3).
        easy_apply_only: Filter for Easy Apply jobs only.
        start: Pagination offset (0, 25, 50, ...).

    Returns:
        Full search URL with query parameters.
    """
    params: dict[str, str] = {
        "keywords": keyword,
        "origin": "JOB_SEARCH_PAGE_JOB_FILTER",
        "sortBy": "DD",
        "start": str(start),
    }

    if location:
        params["location"] = location
    if remote_only:
        params["f_WT"] = "2"
    if easy_apply_only:
        params["f_AL"] = "true"
    if experience_levels:
        params["f_E"] = ",".join(EXPERIENCE_MAP.get(lvl, str(lvl)) for lvl in experience_levels)
    if date_posted in DATE_POSTED_MAP:
        params["f_TPR"] = DATE_POSTED_MAP[date_posted]

    return JOBS_BASE_URL + urlencode(params)


async def _find_with_fallback(page: Page, selectors: list[str]) -> str | None:
    """Try multiple selectors and return the text of the first match.

    Args:
        page: Playwright page instance.
        selectors: List of CSS selectors to try in order.

    Returns:
        Inner text of the first matching element, or None.
    """
    for selector in selectors:
        el = await page.query_selector(selector)
        if el:
            return str((await el.inner_text()).strip())
    return None


async def _scroll_job_list(page: Page) -> None:
    """Scroll the job results sidebar to trigger lazy loading.

    Args:
        page: Playwright page instance.
    """
    for selector in _JOB_LIST_SELECTORS:
        el = await page.query_selector(selector)
        if el:
            for _ in range(5):
                await scroll_element(page, selector, 600)
            return

    for _ in range(5):
        await page.evaluate("window.scrollBy(0, 500)")
        await human_delay(0.5, 1.0)


async def _wait_for_results(page: Page) -> bool:
    """Wait for job results container to appear.

    Args:
        page: Playwright page instance.

    Returns:
        True if results container was found.
    """
    for selector in _JOB_LIST_SELECTORS:
        try:
            await page.wait_for_selector(selector, timeout=15_000)
            log.debug("results_container_found", selector=selector)
            return True
        except Exception:
            continue

    # Last resort: check if ANY job cards exist directly
    await human_delay(3.0, 5.0)
    for card_sel in _JOB_CARD_SELECTORS:
        cards = await page.query_selector_all(card_sel)
        if cards:
            log.debug("results_found_via_cards", selector=card_sel)
            return True

    return False


async def _extract_single_card(page: Page, card: ElementHandle) -> JobListing | None:
    """Extract job details from a single card element.

    Args:
        page: Playwright page instance.
        card: Playwright element handle for the job card.

    Returns:
        JobListing if extraction succeeded, None otherwise.
    """
    # Check for "Applied" badge BEFORE clicking
    already_applied = False
    applied_badge = await card.query_selector(
        '[class*="applied"], .job-card-container__footer-item--applied'
    )
    if applied_badge:
        already_applied = True

    # Click the card to load details in the right panel
    await card.click()
    await human_delay(1.5, 2.5)

    title = await _find_with_fallback(page, _TITLE_SELECTORS) or "Unknown"
    company = await _find_with_fallback(page, _COMPANY_SELECTORS) or "Unknown"

    location = ""
    location_el = await page.query_selector(
        ".job-details-jobs-unified-top-card__primary-description-container"
    )
    if location_el:
        location = (await location_el.inner_text()).strip()

    description = await _extract_description(page)

    easy_apply_btn = await page.query_selector(
        "button.jobs-apply-button, "
        'button[aria-label*="Easy Apply"], '
        'button:has-text("Easy Apply")'
    )
    is_easy_apply = easy_apply_btn is not None

    if not already_applied:
        applied_text = await page.query_selector(
            'span:has-text("Applied"), .artdeco-inline-feedback:has-text("Applied")'
        )
        if applied_text:
            already_applied = True

    job_id = _extract_job_id(page.url)

    return JobListing(
        job_id=job_id,
        title=title,
        company=company,
        location=location,
        description=description,
        url=page.url,
        is_easy_apply=is_easy_apply,
        already_applied=already_applied,
    )


async def _extract_description(page: Page) -> str:
    """Extract job description from the details panel.

    Args:
        page: Playwright page instance.

    Returns:
        Job description text, truncated to 3000 chars.
    """
    for sel in _DESCRIPTION_SELECTORS:
        desc_el = await page.query_selector(sel)
        if desc_el:
            return str((await desc_el.inner_text()).strip()[:3000])
    return ""


async def get_job_listings(page: Page, max_jobs: int = 25) -> list[JobListing]:
    """Extract job listings from the current search results page.

    Scrolls to load lazy-loaded cards, extracts details for each,
    and detects if the user has already applied.

    Args:
        page: Playwright page instance (on a search results page).
        max_jobs: Maximum number of jobs to extract per page.

    Returns:
        List of JobListing objects.
    """
    listings: list[JobListing] = []

    await human_delay(2.0, 4.0)

    if not await _wait_for_results(page):
        log.warning("no_job_results_container")
        return []

    await _scroll_job_list(page)

    # Find job cards with fallback selectors
    job_cards: list[ElementHandle] = []
    for selector in _JOB_CARD_SELECTORS:
        job_cards = await page.query_selector_all(selector)
        if job_cards:
            break

    log.info("job_cards_found", count=len(job_cards))

    for card in job_cards[:max_jobs]:
        try:
            listing = await _extract_single_card(page, card)
            if listing:
                listings.append(listing)
                log.debug(
                    "job_extracted",
                    title=listing.title[:40],
                    company=listing.company,
                    easy_apply=listing.is_easy_apply,
                    already_applied=listing.already_applied,
                )
        except Exception as exc:
            log.warning("job_card_extraction_error", error=str(exc))
            continue

    return listings


def _extract_job_id(url: str) -> str:
    """Extract the job ID from a LinkedIn URL.

    Validates that the ID is numeric. Falls back to a UUID if
    no valid ID can be extracted (fixes BUG-MED-2: empty job_id collision).

    Args:
        url: LinkedIn job URL.

    Returns:
        Numeric job ID string, or a UUID fallback.
    """
    candidates: list[str] = []

    if "currentJobId=" in url:
        candidates.append(url.split("currentJobId=")[1].split("&")[0])
    if "/view/" in url:
        candidates.append(url.split("/view/")[1].split("/")[0].split("?")[0])
    if "/jobs/" in url:
        parts = url.split("/jobs/")
        if len(parts) > 1:
            segment = parts[1].split("/")[0].split("?")[0]
            candidates.append(segment)

    # Return first numeric candidate
    for candidate in candidates:
        if candidate and candidate.isdigit():
            return candidate

    # Fallback: generate UUID to prevent UNIQUE constraint collision
    fallback_id = f"unknown-{uuid.uuid4().hex[:12]}"
    log.warning("job_id_extraction_fallback", url=url[:100], fallback_id=fallback_id)
    return fallback_id


def should_skip_job(
    listing: JobListing,
    blacklist_titles: list[str],
    blacklist_companies: list[str],
) -> tuple[bool, str]:
    """Check if a job should be skipped based on blacklists and state.

    Args:
        listing: The job listing to check.
        blacklist_titles: List of title keywords to skip.
        blacklist_companies: List of company names to skip.

    Returns:
        Tuple of (should_skip, reason).
    """
    if listing.already_applied:
        return True, "Already applied (LinkedIn badge)"

    if not listing.is_easy_apply:
        return True, "Not Easy Apply"

    title_lower = listing.title.lower()
    for keyword in blacklist_titles:
        if keyword.lower() in title_lower:
            return True, f"Blacklisted title keyword: {keyword}"

    company_lower = listing.company.lower()
    for company in blacklist_companies:
        if company.lower() in company_lower:
            return True, f"Blacklisted company: {company}"

    return False, ""
