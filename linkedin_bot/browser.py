"""Playwright browser setup with anti-detection measures.

Loads stealth JS from external file (DEBT-004), uses safe
page.evaluate arguments (B7), and manages browser sessions.
"""

import asyncio
import random
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from playwright.async_api import (
    Browser,
    BrowserContext,
    Page,
    Playwright,
    async_playwright,
)

from linkedin_bot.config import ROOT_DIR, settings
from linkedin_bot.exceptions import StealthError
from linkedin_bot.logger import get_logger

log = get_logger("browser")

COOKIES_DIR = ROOT_DIR / "cookies"
_STEALTH_JS_PATH = Path(__file__).resolve().parent / "stealth.js"

_USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)


@dataclass(slots=True)
class BrowserSession:
    """Holds all Playwright instances for proper lifecycle management."""

    playwright: Playwright
    browser: Browser
    context: BrowserContext
    page: Page


async def human_delay(min_s: float | None = None, max_s: float | None = None) -> None:
    """Simulate a human-like pause with gaussian distribution.

    Args:
        min_s: Minimum delay in seconds (defaults to settings).
        max_s: Maximum delay in seconds (defaults to settings).
    """
    lo = min_s if min_s is not None else settings.min_delay_seconds
    hi = max_s if max_s is not None else settings.max_delay_seconds
    mean = (lo + hi) / 2
    std = (hi - lo) / 4
    delay = random.gauss(mean, std)
    delay = max(lo, min(hi, delay))
    await asyncio.sleep(delay)


async def human_type(page: Page, selector: str, text: str) -> None:
    """Type text into a field with human-like speed.

    Clears the field first, then types char by char with random delays.

    Args:
        page: Playwright page instance.
        selector: CSS selector of the input field.
        text: Text to type.
    """
    el = page.locator(selector).first
    await el.click()
    await asyncio.sleep(random.uniform(0.2, 0.5))
    await el.press("Control+a")
    await el.press("Backspace")
    await asyncio.sleep(random.uniform(0.1, 0.3))
    for char in text:
        await page.keyboard.type(char, delay=random.randint(40, 130))
    await asyncio.sleep(random.uniform(0.1, 0.3))


async def scroll_element(page: Page, selector: str, distance: int = 500) -> None:
    """Scroll a specific element by a given distance.

    Uses parameterized evaluate to avoid f-string JS injection (B7).

    Args:
        page: Playwright page instance.
        selector: CSS selector of the scrollable element.
        distance: Pixels to scroll down.
    """
    try:
        await page.evaluate(
            "(args) => document.querySelector(args.sel)?.scrollBy(0, args.dist)",
            {"sel": selector, "dist": distance},
        )
        await asyncio.sleep(random.uniform(0.8, 1.5))
    except Exception as exc:
        log.debug("scroll_element_fallback", selector=selector, error=str(exc))
        await page.evaluate("(dist) => window.scrollBy(0, dist)", distance)
        await asyncio.sleep(random.uniform(0.5, 1.0))


def _load_stealth_js() -> str:
    """Load stealth JavaScript from external file.

    Returns:
        JavaScript source code.

    Raises:
        StealthError: If stealth.js file is not found.
    """
    if not _STEALTH_JS_PATH.exists():
        msg = f"Stealth JS not found: {_STEALTH_JS_PATH}"
        raise StealthError(msg)
    return _STEALTH_JS_PATH.read_text(encoding="utf-8")


@asynccontextmanager
async def create_browser_session() -> AsyncGenerator[BrowserSession]:
    """Create and manage browser session with proper cleanup.

    Yields a BrowserSession dataclass with all Playwright instances.
    Ensures playwright is properly stopped on exit.

    Yields:
        BrowserSession with playwright, browser, context, and page.
    """
    pw = await async_playwright().start()

    browser: Browser | None = None

    try:
        browser = await pw.chromium.launch(
            headless=settings.headless,
            ignore_default_args=["--enable-automation"],
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-infobars",
                "--disable-extensions",
                "--disable-default-apps",
                "--disable-sync",
            ],
        )

        context = await _setup_context(browser)
        page = await context.new_page()
        await _setup_cdp_overrides(context, page)

        log.info("browser_launched", headless=settings.headless)

        yield BrowserSession(
            playwright=pw,
            browser=browser,
            context=context,
            page=page,
        )

    finally:
        if browser is not None:
            await browser.close()
        await pw.stop()
        log.info("browser_closed")


async def _setup_context(browser: Browser) -> BrowserContext:
    """Create browser context with session restore and stealth injection.

    Args:
        browser: Playwright browser instance.

    Returns:
        Configured BrowserContext.
    """
    COOKIES_DIR.mkdir(exist_ok=True)
    storage_path = COOKIES_DIR / "linkedin_state.json"

    context_args: dict[str, Any] = {
        "viewport": {"width": 1366, "height": 768},
        "user_agent": _USER_AGENT,
        "locale": "en-US",
        "timezone_id": "America/Mexico_City",
        "permissions": [],
    }

    if storage_path.exists():
        context_args["storage_state"] = str(storage_path)
        log.info("session_restored", path=str(storage_path))

    context = await browser.new_context(**context_args)

    # Load stealth JS from external file (DEBT-004 fix)
    stealth_js = _load_stealth_js()
    await context.add_init_script(stealth_js)

    return context


async def _setup_cdp_overrides(context: BrowserContext, page: Page) -> None:
    """Set deeper stealth parameters via CDP.

    Args:
        context: Playwright browser context.
        page: Playwright page instance.
    """
    client = await context.new_cdp_session(page)

    await client.send(
        "Emulation.setHardwareConcurrencyOverride",
        {"hardwareConcurrency": 8},
    )

    await client.send(
        "Network.setUserAgentOverride",
        {
            "userAgent": _USER_AGENT,
            "acceptLanguage": "en-US,en;q=0.9,es;q=0.8",
            "platform": "Linux x86_64",
        },
    )


async def save_session(context: BrowserContext) -> None:
    """Save browser cookies/session for reuse across runs.

    Args:
        context: Playwright browser context to save.
    """
    COOKIES_DIR.mkdir(exist_ok=True)
    storage_path = COOKIES_DIR / "linkedin_state.json"
    await context.storage_state(path=str(storage_path))
    log.info("session_saved", path=str(storage_path))
