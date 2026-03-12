"""DeepSeek AI engine with exponential backoff retry logic and Circuit Breaker.

Uses the OpenAI-compatible SDK with DeepSeek's base URL for
match scoring, form question answering, and cover letter generation.
"""

import asyncio
import json
import time
from typing import Any

from openai import APIConnectionError, APIError, AsyncOpenAI, RateLimitError
from pydantic import BaseModel, Field

from linkedin_bot.config import settings
from linkedin_bot.enums import CircuitState
from linkedin_bot.logger import get_logger

log = get_logger("ai_engine")

# Transient errors that warrant retry
_RETRYABLE_ERRORS = (APIError, APIConnectionError, RateLimitError, TimeoutError)

_NEUTRAL_SCORE = 50


class CircuitBreaker:
    """Implements the Circuit Breaker pattern for AI API protection.

    Args:
        failure_threshold: Consecutive failures before opening.
        recovery_timeout: Seconds to wait before half-open test.
    """

    def __init__(self, failure_threshold: int = 5, recovery_timeout: float = 30.0) -> None:
        self.state = CircuitState.CLOSED
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.failure_count = 0
        self.last_failure_time = 0.0
        self._lock = asyncio.Lock()

    async def record_failure(self) -> None:
        """Record a failure and open circuit if threshold reached."""
        async with self._lock:
            self.failure_count += 1
            self.last_failure_time = time.time()
            if (
                self.failure_count >= self.failure_threshold
                and self.state == CircuitState.CLOSED
            ):
                self.state = CircuitState.OPEN
                log.error("circuit_breaker_opened", failures=self.failure_count)

    async def record_success(self) -> None:
        """Record a success and close the circuit."""
        async with self._lock:
            if self.state != CircuitState.CLOSED:
                self.state = CircuitState.CLOSED
                self.failure_count = 0
                log.info("circuit_breaker_closed")

    async def is_allowed(self) -> bool:
        """Check if a call is allowed through the circuit."""
        async with self._lock:
            if self.state == CircuitState.CLOSED:
                return True

            if self.state == CircuitState.OPEN:
                elapsed = time.time() - self.last_failure_time
                if elapsed > self.recovery_timeout:
                    self.state = CircuitState.HALF_OPEN
                    log.info("circuit_breaker_half_open")
                    return True
                return False

            return True  # HALF_OPEN allows one test call


class JobScores(BaseModel):
    """Structured output schema for bulk scoring."""

    scores: list[int] = Field(description="Match scores in the same order as input.")


class AIEngine:
    """DeepSeek-powered AI engine for job application assistance.

    Uses the OpenAI-compatible SDK with DeepSeek's base URL.
    All API calls include exponential backoff retry logic and a Circuit Breaker.

    Args:
        resume_text: Plain text representation of the resume.
    """

    def __init__(self, resume_text: str) -> None:
        self.resume_text = resume_text
        self.client = AsyncOpenAI(
            api_key=settings.deepseek_api_key.get_secret_value(),
            base_url=settings.deepseek_base_url,
            timeout=30.0,
        )
        self.model = settings.deepseek_model
        self._max_retries = settings.ai_max_retries
        self._retry_delay = settings.ai_retry_delay
        self.circuit_breaker = CircuitBreaker(failure_threshold=5, recovery_timeout=60.0)
        log.info("ai_engine_initialized", model=self.model)

    async def _call_with_retry(
        self,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int = 300,
        temperature: float = 0.7,
        response_format: dict[str, Any] | None = None,
    ) -> str:
        """Make an API call with exponential backoff retry.

        Args:
            system_prompt: System-level instruction for the model.
            user_prompt: User's question or request.
            max_tokens: Maximum tokens in the response.
            temperature: Randomness of the response (0.0-1.0).
            response_format: Optional JSON response format spec.

        Returns:
            Model's text response, or empty string on total failure.
        """
        if not await self.circuit_breaker.is_allowed():
            log.warning("circuit_breaker_active_call_rejected")
            return ""

        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        if response_format:
            kwargs["response_format"] = response_format

        for attempt in range(1, self._max_retries + 1):
            try:
                response = await self.client.chat.completions.create(**kwargs)
                content = response.choices[0].message.content or ""
                token_count = response.usage.total_tokens if response.usage else 0
                log.debug("ai_call_success", attempt=attempt, tokens=token_count)

                await self.circuit_breaker.record_success()
                return content.strip()

            except _RETRYABLE_ERRORS as exc:
                delay = self._retry_delay * (2 ** (attempt - 1))
                log.warning(
                    "ai_call_retry",
                    attempt=attempt,
                    max_retries=self._max_retries,
                    delay=delay,
                    error=str(exc),
                )
                if attempt < self._max_retries:
                    await asyncio.sleep(delay)
                continue

            except Exception as exc:
                log.error("ai_call_fatal_error", error=str(exc), error_type=type(exc).__name__)
                await self.circuit_breaker.record_failure()
                return ""

        log.error("ai_call_all_retries_exhausted", max_retries=self._max_retries)
        await self.circuit_breaker.record_failure()
        return ""

    async def answer_question(self, question: str, job_description: str) -> str:
        """Generate an answer for a job application form question.

        Args:
            question: The question from the application form.
            job_description: Full text of the job posting.

        Returns:
            A concise, professional answer in first person.
        """
        system_prompt = (
            "You are a job application assistant. Answer the question concisely "
            "and professionally in first person. Keep answers under 100 words unless "
            "the question requires more detail.\n\n"
            f"CANDIDATE RESUME:\n{self.resume_text}\n\n"
            f"JOB DESCRIPTION:\n{job_description[:2000]}\n\n"
            "RULES:\n"
            "- Be honest but highlight relevant strengths\n"
            "- Answer in the same language as the question\n"
            "- If it's a yes/no question, answer directly then briefly explain\n"
            "- Never make up certifications or degrees"
        )
        return await self._call_with_retry(system_prompt, question)

    async def calculate_match_score(self, job_title: str, job_description: str) -> int:
        """Calculate how well the candidate matches a job posting.

        Args:
            job_title: Title of the job posting.
            job_description: Full text of the job posting.

        Returns:
            Match score from 0 to 100.
        """
        system_prompt = (
            "You are a job matching expert. Analyze how well the candidate "
            "matches this job posting.\n\n"
            f"CANDIDATE RESUME:\n{self.resume_text}\n\n"
            "Reply with ONLY a single integer from 0 to 100. Nothing else."
        )
        user_prompt = f"Job Title: {job_title}\n\nJob Description:\n{job_description[:2000]}"

        result = await self._call_with_retry(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            max_tokens=10,
            temperature=0.1,
        )
        return self._parse_score(result)

    async def generate_cover_letter(
        self, job_title: str, company: str, job_description: str
    ) -> str:
        """Generate a personalized cover letter.

        Args:
            job_title: Title of the position.
            company: Company name.
            job_description: Full text of the job posting.

        Returns:
            A professional cover letter tailored to the job.
        """
        system_prompt = (
            "You are a professional cover letter writer. Create a concise, "
            "compelling cover letter (max 200 words) that matches the candidate.\n\n"
            f"CANDIDATE RESUME:\n{self.resume_text}\n\n"
            "RULES:\n"
            "- Professional but human tone\n"
            "- Highlight 2-3 most relevant achievements with metrics\n"
            "- No generic templates — make it specific to the role\n"
            "- End with a call to action"
        )
        user_prompt = (
            f"Position: {job_title}\nCompany: {company}\n\n"
            f"Job Description:\n{job_description[:2000]}"
        )
        return await self._call_with_retry(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            max_tokens=400,
            temperature=0.8,
        )

    async def calculate_match_scores_bulk(self, listings: list[dict[str, str]]) -> list[int]:
        """Calculate match scores for a batch of jobs efficiently.

        Args:
            listings: A list of dicts, each with 'title' and 'description'.

        Returns:
            A list of match scores (0-100), matching the input order.
        """
        if not listings:
            return []

        # Graceful Degradation: fallback when circuit is open
        if not await self.circuit_breaker.is_allowed():
            log.warning("circuit_open_fallback_to_heuristic", batch_size=len(listings))
            return [_NEUTRAL_SCORE] * len(listings)

        system_prompt = (
            "You are an expert job matching AI. Given the candidate resume, analyze "
            "multiple job postings at once and return a strict JSON object with a single "
            "key 'scores' containing a list of integers (0 to 100).\n"
            "Each score corresponds to how well the candidate matches the job posting "
            "at the same index.\n\n"
            f"CANDIDATE RESUME:\n{self.resume_text}\n\n"
            "Respond ONLY with valid JSON matching this schema:\n"
            '{ "scores": [95, 20, 50, ...] }'
        )

        user_prompt = self._build_bulk_prompt(listings)

        result = await self._call_with_retry(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            max_tokens=100 + (10 * len(listings)),
            temperature=0.1,
            response_format={"type": "json_object"},
        )

        if not result:
            return [_NEUTRAL_SCORE] * len(listings)

        return self._parse_bulk_scores(result, len(listings))

    @staticmethod
    def _build_bulk_prompt(listings: list[dict[str, str]]) -> str:
        """Build the user prompt for bulk scoring.

        Args:
            listings: Job listings with title and description.

        Returns:
            Formatted prompt string.
        """
        lines: list[str] = []
        for i, job in enumerate(listings):
            desc = job.get("description", "")[:1000]
            lines.append(f"--- JOB {i} ---\nTitle: {job.get('title')}\nDescription:\n{desc}\n")
        return "\n".join(lines)

    @staticmethod
    def _parse_score(result: str) -> int:
        """Parse a single numeric score from AI response.

        Args:
            result: Raw AI response text.

        Returns:
            Score clamped to 0-100, or 50 on parse failure.
        """
        cleaned = "".join(c for c in result if c.isdigit())
        if not cleaned:
            log.warning("match_score_parse_error", raw=result)
            return _NEUTRAL_SCORE

        try:
            score = int(cleaned[:3])
            return max(0, min(100, score))
        except ValueError:
            log.warning("match_score_parse_error", raw=result)
            return _NEUTRAL_SCORE

    @staticmethod
    def _parse_bulk_scores(result: str, expected_count: int) -> list[int]:
        """Parse bulk scores from AI JSON response.

        Args:
            result: Raw JSON response text.
            expected_count: Expected number of scores.

        Returns:
            List of scores clamped to 0-100.
        """
        try:
            data = json.loads(result)
            scores: list[int] = data.get("scores", [])

            # Pad or truncate to match length
            if len(scores) < expected_count:
                scores.extend([_NEUTRAL_SCORE] * (expected_count - len(scores)))
            elif len(scores) > expected_count:
                scores = scores[:expected_count]

            return [max(0, min(100, int(score))) for score in scores]
        except (json.JSONDecodeError, ValueError, TypeError) as exc:
            log.error("bulk_match_score_parse_error", error=str(exc), raw=result)
            return [_NEUTRAL_SCORE] * expected_count
