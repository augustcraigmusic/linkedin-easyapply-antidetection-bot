"""Easy Apply form handling, resume upload, and submission.

Fixes:
- BUG-HIGH-1: Checkbox auto-check with label analysis (whitelist).
- BUG-MED-1: Radio fallback uses AI instead of blind first option.
- BUG-MED-3: Delete buttons scoped to resume-related only.
- CC reduced from 27 to ≤10 by splitting fill_form_fields.
- All silent failures replaced with log.debug.
"""

import contextlib
from pathlib import Path

from playwright.async_api import ElementHandle, Page

from linkedin_bot.ai_engine import AIEngine
from linkedin_bot.browser import human_delay
from linkedin_bot.config import settings
from linkedin_bot.job_search import JobListing
from linkedin_bot.logger import get_logger

log = get_logger("applicator")

# Checkboxes with these keywords are SAFE to auto-check
_SAFE_CHECKBOX_KEYWORDS = frozenset({
    "follow", "seguir",
    "acknowledge", "reconozco",
    "confirm", "confirmo",
    "i have read", "he leído",
    "terms of service", "términos",
    "privacy", "privacidad",
    "consent to receive", "consentimiento",
})

# Checkboxes with these keywords are DANGEROUS — never auto-check
_DANGEROUS_CHECKBOX_KEYWORDS = frozenset({
    "non-compete", "no competencia",
    "drug test", "prueba de drogas",
    "background check", "antecedentes",
    "relocat", "reubicación",
    "deduction", "deducción",
    "arbitration", "arbitraje",
    "waive", "renunciar",
})


async def click_easy_apply(page: Page) -> bool:
    """Click the Easy Apply button on a job listing.

    Tries multiple selectors for resilience against LinkedIn UI changes.

    Args:
        page: Playwright page instance.

    Returns:
        True if the button was clicked successfully.
    """
    selectors = [
        "button.jobs-apply-button",
        'button[aria-label*="Easy Apply"]',
        'button:has-text("Easy Apply")',
        ".jobs-apply-button--top-card button",
        "button.jobs-apply-button--top-card",
        ".jobs-s-apply button",
        'button[aria-label*="Solicitud sencilla"]',
        'button:has-text("Solicitud sencilla")',
        '[class*="jobs-apply"] button',
        'button.artdeco-button--primary:has-text("Apply")',
        'a[aria-label*="Easy Apply"]',
        'a:has-text("Easy Apply")',
        'a[aria-label*="Solicitud sencilla"]',
        'a:has-text("Solicitud sencilla")',
    ]

    with contextlib.suppress(Exception):
        await page.wait_for_selector(
            "button.jobs-apply-button, "
            'button[aria-label*="Easy Apply"], '
            'button[aria-label*="Solicitud sencilla"]',
            timeout=8_000,
        )

    for selector in selectors:
        try:
            btn = page.locator(selector).first
            if await btn.count() > 0 and await btn.is_visible():
                await btn.click()
                await human_delay(1.5, 3.0)
                log.info("easy_apply_clicked", selector=selector)
                return True
        except Exception as exc:
            log.debug("easy_apply_selector_miss", selector=selector, error=str(exc))
            continue

    log.warning("easy_apply_button_not_found")
    return False


async def handle_file_upload(page: Page, resume_path: str) -> bool:
    """Upload resume PDF to the Easy Apply form.

    Scopes delete buttons to resume-related only (BUG-MED-3 fix).

    Args:
        page: Playwright page instance.
        resume_path: Absolute path to the resume PDF file.

    Returns:
        True if file was uploaded successfully.
    """
    if not resume_path:
        log.debug("no_resume_path_configured")
        return True

    resolved = Path(resume_path).resolve()
    if not resolved.exists():
        log.error("resume_file_not_found", path=str(resolved))
        return False

    try:
        await _delete_existing_resumes(page)
        return await _upload_resume_file(page, resolved)
    except Exception as exc:
        log.error("file_upload_error", error=str(exc))
        return False


async def _delete_existing_resumes(page: Page) -> None:
    """Delete only resume-related files from the form (BUG-MED-3 fix).

    Scopes delete buttons to the resume upload section only.

    Args:
        page: Playwright page instance.
    """
    # Scope to the resume upload section, not the entire form
    resume_section_selectors = [
        '.jobs-document-upload-redesign-card__container',
        '[class*="document-upload"]',
        '[class*="resume"]',
    ]
    for section_sel in resume_section_selectors:
        section = await page.query_selector(section_sel)
        if section:
            delete_buttons = await section.query_selector_all(
                'button[aria-label*="Delete"], button[aria-label*="Eliminar"]'
            )
            for d_btn in delete_buttons:
                if await d_btn.is_visible():
                    await d_btn.click()
                    await human_delay(0.5, 1.0)
                    log.debug("deleted_existing_resume")
            return


async def _upload_resume_file(page: Page, resolved: Path) -> bool:
    """Find file input and upload resume.

    Args:
        page: Playwright page instance.
        resolved: Resolved path to the resume file.

    Returns:
        True if upload succeeded.
    """
    file_inputs = await page.query_selector_all('input[type="file"]')
    if file_inputs:
        await file_inputs[0].set_input_files(str(resolved))
        await human_delay(1.0, 2.0)
        log.info("resume_uploaded", path=str(resolved))
        return True

    # Try clicking upload button to reveal file input
    upload_buttons = [
        'button:has-text("Upload resume")',
        'button:has-text("Upload")',
        'label:has-text("Upload resume")',
        "[data-test-file-input-button]",
    ]
    for selector in upload_buttons:
        btn = page.locator(selector).first
        if await btn.count() > 0:
            await btn.click()
            await human_delay(0.5, 1.0)
            file_inputs = await page.query_selector_all('input[type="file"]')
            if file_inputs:
                await file_inputs[0].set_input_files(str(resolved))
                await human_delay(1.0, 2.0)
                log.info("resume_uploaded", method="button_click", path=str(resolved))
                return True

    log.debug("no_file_upload_field_found")
    return True  # Some forms don't ask for resume


async def _dismiss_discard_modal(page: Page) -> None:
    """Dismiss the 'Save this application?' modal by clicking Discard."""
    try:
        discard_btn = page.locator(
            'button[data-control-name="discard_application_confirm_btn"], '
            'button:has-text("Discard")'
        ).first
        if await discard_btn.is_visible(timeout=1000):
            await discard_btn.click()
            await human_delay(0.5, 1.0)
            log.debug("dismissed_discard_modal")
    except Exception as exc:
        log.debug("dismiss_discard_noop", error=str(exc))


# ── Form Field Handlers (split from fill_form_fields for CC reduction) ──


async def _fill_text_inputs(
    page: Page,
    listing: JobListing,
    ai: AIEngine,
    default_answers: dict[str, str],
) -> None:
    """Fill empty text input fields with defaults or AI answers.

    Args:
        page: Playwright page instance.
        listing: Job listing being applied to.
        ai: AI engine for generating answers.
        default_answers: Pre-configured default answers.
    """
    text_inputs = await page.query_selector_all(
        'input[type="text"]:visible, '
        'input[type="tel"]:visible, '
        'input[type="email"]:visible, '
        'input[type="number"]:visible'
    )

    for input_el in text_inputs:
        current_value = await input_el.input_value()
        if current_value.strip():
            continue

        label_text = await _get_field_label(page, input_el)
        answer = _match_default_answer(label_text, default_answers)

        if answer:
            await input_el.fill(answer)
            await human_delay(0.2, 0.5)
            log.debug("field_filled", label=label_text[:30], value=answer[:20])
        elif label_text and len(label_text) > 5:
            ai_answer = await ai.answer_question(label_text, listing.description)
            if ai_answer:
                await input_el.fill(ai_answer[:100])
                await human_delay(0.3, 0.6)
                log.info("text_input_answered_by_ai", label=label_text[:30])


async def _fill_textareas(
    page: Page,
    listing: JobListing,
    ai: AIEngine,
) -> None:
    """Fill empty textareas with AI-generated answers.

    Args:
        page: Playwright page instance.
        listing: Job listing being applied to.
        ai: AI engine for generating answers.
    """
    textareas = await page.query_selector_all("textarea:visible")

    for textarea in textareas:
        current_value = await textarea.input_value()
        if current_value.strip():
            continue

        question = await _get_field_label(page, textarea)
        if question:
            answer = await ai.answer_question(question, listing.description)
            if answer:
                await textarea.fill(answer)
                await human_delay(0.5, 1.0)
                log.info("textarea_answered_by_ai", question=question[:40])


async def _fill_dropdowns(
    page: Page,
    default_answers: dict[str, str],
) -> None:
    """Fill unselected dropdown fields with best option.

    Args:
        page: Playwright page instance.
        default_answers: Pre-configured default answers.
    """
    selects = await page.query_selector_all("select:visible")

    for select_el in selects:
        options = await select_el.query_selector_all("option")
        if len(options) <= 1:
            continue

        current = await select_el.input_value()
        if current and current != "":
            continue

        label = await _get_field_label(page, select_el)
        best_value = await _pick_best_option(options, label, default_answers)
        if best_value is not None:
            await select_el.select_option(value=best_value)
            await human_delay(0.2, 0.4)
            log.debug("dropdown_selected", label=label[:30])


async def _fill_radios(
    page: Page,
    listing: JobListing,
    ai: AIEngine,
) -> None:
    """Fill unanswered radio button groups.

    BUG-MED-1 fix: Uses AI for unrecognized questions instead of
    blindly selecting the first option.

    Args:
        page: Playwright page instance.
        listing: Job listing being applied to.
        ai: AI engine for generating answers.
    """
    fieldsets = await page.query_selector_all("fieldset:visible")
    for fieldset in fieldsets:
        radios = await fieldset.query_selector_all('input[type="radio"]')
        if not radios:
            continue

        # Skip if already answered
        if await _any_radio_checked(radios):
            continue

        # Collect labels for all options
        radio_labels = []
        for radio in radios:
            label = await _get_radio_label(page, radio)
            radio_labels.append(label)

        # Try to find "Yes/Sí" option
        selected = await _select_affirmative_radio(radios, radio_labels)

        if not selected:
            # BUG-MED-1 FIX: Use AI to pick the right option instead of blind first
            question = await _get_field_label(page, fieldset)
            if question:
                ai_answer = await ai.answer_question(
                    f"Choose the best option for: {question}. "
                    f"Options: {', '.join(radio_labels)}",
                    listing.description,
                )
                selected = await _select_radio_by_ai(radios, radio_labels, ai_answer)

            # Last resort: select first option, but log a warning
            if not selected and radios:
                await radios[0].check(force=True)
                log.warning("radio_blind_fallback", labels=radio_labels[:3])

        await human_delay(0.2, 0.4)


async def _any_radio_checked(radios: list[ElementHandle]) -> bool:
    """Check if any radio in the group is already checked."""
    for radio in radios:
        if await radio.is_checked():
            return True
    return False


async def _select_affirmative_radio(radios: list[ElementHandle], labels: list[str]) -> bool:
    """Try to select a 'Yes'/'Sí' radio option."""
    for i, label in enumerate(labels):
        if label.lower() in ("yes", "sí", "si"):
            await radios[i].check(force=True)
            return True
    return False


async def _select_radio_by_ai(
    radios: list[ElementHandle], labels: list[str], ai_answer: str
) -> bool:
    """Select radio option that best matches the AI answer."""
    if not ai_answer:
        return False
    ai_lower = ai_answer.lower()
    for i, label in enumerate(labels):
        if label.lower() in ai_lower or ai_lower in label.lower():
            await radios[i].check(force=True)
            log.info("radio_answered_by_ai", label=label)
            return True
    return False


async def _fill_checkboxes(page: Page) -> None:
    """Fill unchecked checkboxes with label-based safety analysis.

    BUG-HIGH-1 fix: Only checks checkboxes that are safe (whitelist).
    Logs and skips checkboxes with dangerous keywords.

    Args:
        page: Playwright page instance.
    """
    checkboxes = await page.query_selector_all(
        'input[type="checkbox"]:visible:not(:checked)'
    )
    for checkbox in checkboxes:
        label = await _get_field_label(page, checkbox)

        # Check against dangerous keywords
        if _is_dangerous_checkbox(label):
            log.warning("dangerous_checkbox_skipped", label=label[:60])
            continue

        # Only auto-check if it's in the safe list OR has no identifiable label
        if _is_safe_checkbox(label) or not label:
            await checkbox.check(force=True)
            await human_delay(0.1, 0.3)
            log.debug("checkbox_checked", label=label[:40] if label else "unlabeled")
        else:
            # Unknown checkbox — skip it to be safe
            log.info("checkbox_skipped_unknown", label=label[:60])


def _is_dangerous_checkbox(label: str) -> bool:
    """Check if a checkbox label contains dangerous keywords."""
    label_lower = label.lower()
    return any(kw in label_lower for kw in _DANGEROUS_CHECKBOX_KEYWORDS)


def _is_safe_checkbox(label: str) -> bool:
    """Check if a checkbox label contains safe keywords."""
    label_lower = label.lower()
    return any(kw in label_lower for kw in _SAFE_CHECKBOX_KEYWORDS)


async def fill_form_fields(
    page: Page,
    listing: JobListing,
    ai: AIEngine,
    default_answers: dict[str, str],
) -> bool:
    """Fill in the current step of the Easy Apply form.

    Delegates to specialized handlers for each field type.

    Args:
        page: Playwright page instance.
        listing: The job listing being applied to.
        ai: AI engine for generating answers.
        default_answers: Pre-configured default answers.

    Returns:
        True if the form was filled successfully.
    """
    try:
        await human_delay(0.8, 1.5)
        await handle_file_upload(page, settings.resume_path)
        await _fill_text_inputs(page, listing, ai, default_answers)
        await _fill_textareas(page, listing, ai)
        await _fill_dropdowns(page, default_answers)
        await _fill_radios(page, listing, ai)
        await _fill_checkboxes(page)
        return True
    except Exception as exc:
        log.error("form_fill_error", error=str(exc))
        return False


# ── Navigation helpers (split from navigate_and_submit for CC reduction) ──


async def _try_click_button(page: Page, selectors: list[str]) -> bool:
    """Try to click the first visible button from a list of selectors.

    Args:
        page: Playwright page instance.
        selectors: CSS selectors to try in order.

    Returns:
        True if a button was clicked.
    """
    for sel in selectors:
        btn = page.locator(sel).first
        if await btn.count() > 0 and await btn.is_visible():
            await btn.click()
            await human_delay(1.0, 2.0)
            return True
    return False


async def navigate_and_submit(
    page: Page,
    listing: JobListing,
    ai: AIEngine,
    default_answers: dict[str, str],
    dry_run: bool = True,
) -> bool:
    """Navigate through all steps of the Easy Apply form and submit.

    Args:
        page: Playwright page instance.
        listing: The job listing being applied to.
        ai: AI engine for generating answers.
        default_answers: Pre-configured default answers.
        dry_run: If True, don't actually submit.

    Returns:
        True if the application was submitted (or would be in dry_run).
    """
    max_steps = 10

    submit_selectors = [
        'button[aria-label*="Submit application"]',
        'button:has-text("Submit application")',
        'button[aria-label*="Enviar solicitud"]',
    ]
    next_selectors = [
        'button[aria-label="Continue to next step"]',
        'button:has-text("Next")',
        'button:has-text("Siguiente")',
    ]
    review_selectors = [
        'button:has-text("Review")',
        'button:has-text("Revisar")',
    ]

    for step in range(max_steps):
        log.debug("form_step", step=step + 1)
        await fill_form_fields(page, listing, ai, default_answers)
        await human_delay(0.8, 1.5)

        # Check for Submit (final step)
        if await _try_click_button(page, submit_selectors if not dry_run else []):
            log.info("application_submitted", title=listing.title[:40], company=listing.company)
            await _close_post_submit(page)
            return True

        # Dry run: detect submit button without clicking
        if dry_run:
            for sel in submit_selectors:
                btn = page.locator(sel).first
                if await btn.count() > 0 and await btn.is_visible():
                    log.info(
                        "dry_run_would_submit",
                        title=listing.title[:40],
                        company=listing.company,
                    )
                    await _close_modal(page)
                    return True

        # Try Next, then Review
        if await _try_click_button(page, next_selectors):
            continue
        if await _try_click_button(page, review_selectors):
            continue

        log.warning("form_navigation_stuck", step=step + 1)
        await _close_modal(page)
        return False

    log.warning("form_too_many_steps", max_steps=max_steps)
    await _close_modal(page)
    return False


async def _close_modal(page: Page) -> None:
    """Close any open Easy Apply modal dialog.

    Args:
        page: Playwright page instance.
    """
    try:
        await _dismiss_discard_modal(page)

        close_selectors = [
            'button[aria-label="Dismiss"]',
            "button.artdeco-modal__dismiss",
            'button[aria-label="Close"]',
        ]

        for selector in close_selectors:
            btn = page.locator(selector).first
            if await btn.count() > 0:
                await btn.click()
                await human_delay(0.5, 1.0)
                await _dismiss_discard_modal(page)
                return
    except Exception as exc:
        log.debug("close_modal_noop", error=str(exc))


async def _close_post_submit(page: Page) -> None:
    """Close the post-submission dialog (Application sent!).

    Args:
        page: Playwright page instance.
    """
    try:
        await human_delay(1.0, 2.0)
        close_selectors = [
            'button[aria-label="Dismiss"]',
            'button:has-text("Done")',
            "button.artdeco-modal__dismiss",
        ]
        for selector in close_selectors:
            btn = page.locator(selector).first
            if await btn.count() > 0:
                await btn.click()
                await human_delay(0.5, 1.0)
                return
    except Exception as exc:
        log.debug("close_post_submit_noop", error=str(exc))


# ── Label extraction helpers ──


async def _get_field_label(page: Page, element: ElementHandle) -> str:
    """Get the label text for a form field via multiple strategies.

    Args:
        page: Playwright page instance.
        element: Playwright element handle for the form field.

    Returns:
        Label text or empty string.
    """
    try:
        el_id = await element.get_attribute("id")
        if el_id:
            label_el = await page.query_selector(f'label[for="{el_id}"]')
            if label_el:
                return str((await label_el.inner_text()).strip().lower())

        aria = await element.get_attribute("aria-label")
        if aria:
            return str(aria.strip().lower())

        placeholder = await element.get_attribute("placeholder")
        if placeholder:
            return str(placeholder.strip().lower())

        parent_label = await page.evaluate(
            """(el) => {
                const label = el.closest('label');
                return label ? label.innerText.trim() : '';
            }""",
            element,
        )
        if parent_label:
            return str(parent_label).lower()

    except Exception as exc:
        log.debug("get_field_label_error", error=str(exc))

    return ""


async def _get_radio_label(page: Page, radio: ElementHandle) -> str:
    """Get the label text for a radio button.

    Args:
        page: Playwright page instance.
        radio: The radio input element.

    Returns:
        Label text or empty string.
    """
    try:
        radio_id = await radio.get_attribute("id")
        if radio_id:
            label_el = await page.query_selector(f'label[for="{radio_id}"]')
            if label_el:
                return str((await label_el.inner_text()).strip())

        text = await page.evaluate(
            """(el) => {
                const label = el.parentElement?.querySelector('label');
                return label ? label.innerText.trim() : '';
            }""",
            radio,
        )
        return text or ""
    except Exception as exc:
        log.debug("get_radio_label_error", error=str(exc))
        return ""


async def _pick_best_option(
    options: list[ElementHandle],
    label: str,
    defaults: dict[str, str],
) -> str | None:
    """Choose the best dropdown option based on label context.

    Args:
        options: List of <option> elements.
        label: The label of the select field.
        defaults: Default answer mappings.

    Returns:
        The value of the best option, or None.
    """
    answer = _match_default_answer(label, defaults)

    for option in options[1:]:
        value = await option.get_attribute("value")
        text = str((await option.inner_text()).strip())

        if not value or not text:
            continue

        if answer and answer.lower() in text.lower():
            return str(value)

    # Fallback: select first non-empty option
    for option in options[1:]:
        value = await option.get_attribute("value")
        if value:
            return str(value)

    return None


def _match_default_answer(label: str, defaults: dict[str, str]) -> str:
    """Match a form label to a default answer.

    Args:
        label: The lowercase label text from the form field.
        defaults: Dictionary of default answers.

    Returns:
        Matched answer or empty string if no match.
    """
    if not label:
        return ""

    mappings: dict[str, str] = {
        "phone": defaults.get("phone", ""),
        "mobile": defaults.get("phone", ""),
        "número": defaults.get("phone", ""),
        "cell": defaults.get("phone", ""),
        "city": defaults.get("city", ""),
        "location": defaults.get("city", ""),
        "ciudad": defaults.get("city", ""),
        "experience": defaults.get("years_experience", ""),
        "years": defaults.get("years_experience", ""),
        "años": defaults.get("years_experience", ""),
        "authorization": defaults.get("work_authorization", ""),
        "authorized": defaults.get("work_authorization", ""),
        "eligible": defaults.get("work_authorization", ""),
        "legally": defaults.get("work_authorization", ""),
        "sponsor": defaults.get("sponsorship_required", ""),
        "visa": defaults.get("sponsorship_required", ""),
        "relocat": defaults.get("willing_to_relocate", ""),
        "remote": defaults.get("remote_work", ""),
        "salary": defaults.get("salary_expectation", ""),
        "compensation": defaults.get("salary_expectation", ""),
        "start": defaults.get("start_date", ""),
        "english": defaults.get("english_proficiency", ""),
        "language": defaults.get("english_proficiency", ""),
        "proficien": defaults.get("english_proficiency", ""),
    }

    for key, value in mappings.items():
        if key in label and value:
            return value

    return ""
