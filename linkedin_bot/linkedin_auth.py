"""LinkedIn authentication and session management.

CC reduced from 14 to ≤7 by extracting helper functions.
"""

from playwright.async_api import BrowserContext, Page

from linkedin_bot.browser import human_delay, human_type, save_session
from linkedin_bot.config import settings
from linkedin_bot.logger import get_logger

log = get_logger("auth")

LOGIN_URL = "https://www.linkedin.com/login"
FEED_URL = "https://www.linkedin.com/feed/"

_LOGGED_IN_PATHS = ("/feed", "/mynetwork")


def _is_on_feed(url: str) -> bool:
    """Check if a URL indicates a logged-in state."""
    return any(path in url for path in _LOGGED_IN_PATHS)


async def is_logged_in(page: Page) -> bool:
    """Check if the user is currently logged into LinkedIn.

    Args:
        page: Playwright page instance.

    Returns:
        True if logged in, False otherwise.
    """
    try:
        await page.goto(FEED_URL, wait_until="domcontentloaded", timeout=20_000)
        await human_delay(1.5, 3.0)

        if _is_on_feed(page.url):
            log.info("already_logged_in")
            return True

        nav = await page.query_selector('nav[aria-label="Primary"]')
        if nav:
            log.info("already_logged_in", method="nav_check")
            return True

        return False
    except Exception as exc:
        log.warning("login_check_failed", error=str(exc))
        return False


async def _fill_credentials(page: Page) -> None:
    """Navigate to login page and fill credentials.

    Args:
        page: Playwright page instance.
    """
    await page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=20_000)
    await human_delay(1.5, 3.0)

    await human_type(page, 'input[id="username"]', settings.linkedin_email)
    await human_delay(0.5, 1.0)

    await human_type(
        page, 'input[id="password"]', settings.linkedin_password.get_secret_value()
    )
    await human_delay(0.8, 1.5)

    submit = page.locator('button[type="submit"]')
    await submit.click()
    await human_delay(4.0, 7.0)


async def _handle_security_challenge(page: Page) -> bool:
    """Wait for manual resolution of security challenges.

    Args:
        page: Playwright page instance.

    Returns:
        True if challenge was resolved, False on timeout.
    """
    if not any(kw in page.url for kw in ("checkpoint", "challenge", "security")):
        return True

    log.warning(
        "security_challenge_detected",
        hint="Complete the verification manually in the browser window",
        url=page.url,
    )
    try:
        await page.wait_for_url("**/feed/**", timeout=120_000)
        return True
    except Exception:
        return _is_on_feed(page.url)


async def login(page: Page, context: BrowserContext) -> bool:
    """Log into LinkedIn with configured credentials.

    Args:
        page: Playwright page instance.
        context: Browser context for saving session.

    Returns:
        True if login succeeded, False otherwise.
    """
    if not settings.linkedin_email or not settings.linkedin_password.get_secret_value():
        log.error("missing_credentials", hint="Set LINKEDIN_EMAIL and LINKEDIN_PASSWORD in .env")
        return False

    try:
        if await is_logged_in(page):
            return True

        log.info("logging_in", email=settings.linkedin_email[:5] + "***")
        await _fill_credentials(page)

        if not await _handle_security_challenge(page):
            log.error("manual_verification_timeout")
            return False

        # Verify login success (with delayed retry)
        for _ in range(2):
            if _is_on_feed(page.url):
                log.info("login_success")
                await save_session(context)
                return True
            await human_delay(3.0, 5.0)

        log.error("login_failed", current_url=page.url)
        return False

    except Exception as exc:
        log.error("login_error", error=str(exc))
        return False
