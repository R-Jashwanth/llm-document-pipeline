"""
LLM Wrapper Module for the Autonomous Business Document Agent.

Uses Groq (llama-3.3-70b) as the primary provider with Gemini as fallback.
All upstream modules import GeminiClient — the interface is unchanged.
"""

import json
import re
import time
from typing import Optional

from config import settings
from utils import LLMException, logger


def _clean_json_markdown(raw_string: str) -> str:
    cleaned = raw_string.strip()
    if cleaned.startswith("```json"):
        cleaned = cleaned[7:]
    elif cleaned.startswith("```"):
        cleaned = cleaned[3:]
    if cleaned.endswith("```"):
        cleaned = cleaned[:-3]
    return cleaned.strip()


def _parse_retry_delay(error_str: str) -> float:
    match = re.search(r"['\"]retryDelay['\"]\s*:\s*['\"](\d+(?:\.\d+)?)s['\"]", error_str)
    if match:
        return float(match.group(1))
    match = re.search(r"retry in (\d+(?:\.\d+)?)s", error_str, re.IGNORECASE)
    if match:
        return float(match.group(1))
    return 0.0


def _parse_groq_wait(error_str: str) -> float:
    """Extract wait seconds from Groq rate limit messages like 'try again in 3m10.08s'."""
    match = re.search(r"try again in\s+(?:(\d+)h)?(?:(\d+)m)?(?:(\d+(?:\.\d+)?)s)?", error_str, re.IGNORECASE)
    if match:
        hours = float(match.group(1) or 0)
        mins = float(match.group(2) or 0)
        secs = float(match.group(3) or 0)
        total = hours * 3600 + mins * 60 + secs
        # Cap at 120s — if quota resets in hours, fall through to Gemini
        return min(total, 120.0)
    return 0.0


def _groq_generate(
    prompt: str,
    system_prompt: Optional[str],
    response_format: str,
) -> str:
    """Call Groq API. Tries llama-3.3-70b-versatile first, falls back to llama-3.1-8b-instant."""
    try:
        from groq import Groq
    except ImportError as e:
        raise LLMException(
            "groq package not installed. Run: pip install groq",
            details=str(e),
        ) from e

    client = Groq(api_key=settings.groq_api_key)

    # Model priority: 70b for quality, 8b as fallback when 70b quota exhausted
    models_to_try = [
        ("llama-3.3-70b-versatile", 4096),
        ("llama-3.1-8b-instant", 2048),
    ]

    last_error = None
    for model, max_tok in models_to_try:
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        kwargs: dict = {"model": model, "messages": messages, "temperature": 0.2, "max_tokens": max_tok}
        if response_format == "json":
            kwargs["response_format"] = {"type": "json_object"}

        max_attempts = 3
        model_exhausted = False

        for attempt in range(1, max_attempts + 1):
            try:
                logger.info(
                    f"Requesting Groq ({model}) | Format: {response_format} | Attempt {attempt}/{max_attempts}"
                )
                response = client.chat.completions.create(**kwargs)
                result_text = (response.choices[0].message.content or "").strip()

                if not result_text:
                    raise LLMException("Groq returned empty response.")

                if response_format == "json":
                    cleaned = _clean_json_markdown(result_text)
                    try:
                        json.loads(cleaned)
                        return cleaned
                    except json.JSONDecodeError as jde:
                        if attempt == max_attempts:
                            raise LLMException(
                                "Failed to parse JSON from Groq response.",
                                details=f"Raw: {result_text}",
                            ) from jde
                else:
                    return result_text

            except LLMException:
                raise
            except Exception as err:
                err_str = str(err)
                logger.warning(f"Groq ({model}) error on attempt {attempt}: {err}")

                # Daily token quota exhausted — try next model
                if "tokens per day" in err_str.lower() or "tpd" in err_str.lower():
                    logger.warning(f"Groq ({model}) daily quota exhausted, trying next model...")
                    model_exhausted = True
                    last_error = err_str
                    break

                # Request too large for this model — try next model
                if "request too large" in err_str.lower() or "413" in err_str:
                    logger.warning(f"Groq ({model}) context too large, trying next model...")
                    model_exhausted = True
                    last_error = err_str
                    break

                # Decommissioned model — try next
                if "decommissioned" in err_str.lower():
                    model_exhausted = True
                    last_error = err_str
                    break

                if attempt == max_attempts:
                    last_error = err_str
                    model_exhausted = True
                    break

                wait = _parse_groq_wait(err_str)
                time.sleep(wait if wait else 10 * attempt)

        if not model_exhausted:
            break  # Success already returned above

    raise LLMException(
        "All Groq models failed.",
        details=str(last_error),
    )


def _gemini_generate(
    prompt: str,
    system_prompt: Optional[str],
    response_format: str,
) -> str:
    """Call Gemini API as fallback."""
    from google import genai
    from google.genai import types
    from google.genai.errors import APIError

    client = genai.Client(api_key=settings.gemini_api_key)
    model_name = settings.gemini_model
    mime_type = "application/json" if response_format == "json" else "text/plain"
    config = types.GenerateContentConfig(
        system_instruction=system_prompt,
        response_mime_type=mime_type,
        temperature=0.2,
    )

    max_attempts = 4
    base_delay = 15.0

    for attempt in range(1, max_attempts + 1):
        try:
            logger.info(
                f"Requesting Gemini ({model_name}) | Format: {response_format} | Attempt {attempt}/{max_attempts}"
            )
            response = client.models.generate_content(
                model=model_name, contents=prompt, config=config
            )
            if not response.text:
                raise LLMException("Gemini returned empty response.")

            result_text = response.text.strip()

            if response_format == "json":
                cleaned = _clean_json_markdown(result_text)
                try:
                    json.loads(cleaned)
                    return cleaned
                except json.JSONDecodeError as jde:
                    if attempt == max_attempts:
                        raise LLMException(
                            "Failed to parse JSON from Gemini response.",
                            details=f"Raw: {result_text}",
                        ) from jde
            else:
                return result_text

        except APIError as api_err:
            logger.warning(f"Gemini APIError on attempt {attempt}: {api_err}")
            if attempt == max_attempts:
                raise LLMException(
                    f"Gemini API failed after {max_attempts} attempts.",
                    details=str(api_err),
                ) from api_err
            retry_delay = _parse_retry_delay(str(api_err))
            backoff = max(retry_delay, base_delay * (2 ** (attempt - 1)))
            logger.info(f"Backing off {backoff:.1f}s before retry (attempt {attempt + 1}/{max_attempts})…")
            time.sleep(backoff)

        except LLMException:
            raise

        except Exception as other_err:
            logger.warning(f"Unexpected Gemini error on attempt {attempt}: {other_err}")
            if attempt == max_attempts:
                raise LLMException(
                    f"Unexpected Gemini error after {max_attempts} attempts.",
                    details=str(other_err),
                ) from other_err
            time.sleep(base_delay)

    raise LLMException("Gemini generation failed.")


class GeminiClient:
    """
    Unified LLM client. Uses Groq as primary provider, Gemini as fallback.
    Interface is identical to the original GeminiClient — no upstream changes needed.
    """

    def __init__(self) -> None:
        self._groq_available = bool(settings.groq_api_key)
        if self._groq_available:
            logger.info("LLM provider: Groq (primary), Gemini (fallback)")
        else:
            logger.info("LLM provider: Gemini only (no GROQ_API_KEY set)")

    def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        response_format: str = "text",
    ) -> str:
        # Try Groq first if available
        if self._groq_available:
            try:
                return _groq_generate(prompt, system_prompt, response_format)
            except LLMException as e:
                logger.error(f"Groq failed: {e.message} | Details: {e.details}")
                logger.warning("Falling back to Gemini...")

        # Fallback to Gemini
        return _gemini_generate(prompt, system_prompt, response_format)
