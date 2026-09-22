"""
Reflection / Self-Check Module for the Autonomous Business Document Agent.

The ReflectionAgent acts as a quality-control layer over the generated
business document.

The reflection stage is intentionally defensive:

1. Audits the generated document.
2. Checks completeness and structural integrity.
3. Detects accidental truncation.
4. Detects missing sections.
5. Detects placeholders.
6. Detects suspiciously short revisions.
7. Accepts an improved version only when it is demonstrably safe.
8. Falls back to the previous valid document when reflection produces
   a degraded result.

This prevents the reflection stage from accidentally destroying a
good multi-section document.
"""

import json
import re
from typing import List

from llm import GeminiClient
from models import ReflectionOutput
from prompts import REFLECTION_SYSTEM_PROMPT
from utils import ReflectionException, logger


class ReflectionAgent:
    """
    Audits and improves generated business documents.

    The ReflectionAgent is a closed-loop quality-control component.
    However, it never blindly trusts an LLM-generated revision.
    """

    # A revision that is dramatically shorter than the original is
    # considered suspicious.
    MIN_RETENTION_RATIO = 0.75

    # A document should contain meaningful content.
    MIN_DOCUMENT_WORDS = 300

    # Common placeholders that should not survive into the final document.
    PLACEHOLDER_PATTERNS = [
        r"\[TBD\]",
        r"\[TODO\]",
        r"\[INSERT[^\]]*\]",
        r"\[ADD[^\]]*\]",
        r"\[FILL[^\]]*\]",
        r"\[YOUR[^\]]*\]",
        r"<TBD>",
        r"<TODO>",
    ]

    def __init__(
        self,
        client: GeminiClient | None = None,
    ) -> None:
        """
        Initialize the ReflectionAgent.
        """

        self.client = client or GeminiClient()

    # ==================================================================
    # PUBLIC REFLECTION METHOD
    # ==================================================================

    def reflect_and_improve(
        self,
        request: str,
        document_type: str,
        assumptions: List[str],
        content: str,
        max_reflection_loops: int = 1,
    ) -> tuple[str, List[str]]:
        """
        Audit and improve the generated document.

        The original content is treated as the baseline valid document.

        A reflection-generated revision is accepted only when:
        - it is non-empty
        - it is not suspiciously short
        - it retains the major structure
        - it does not lose most headings
        - it does not contain obvious truncation
        - it does not introduce placeholders

        Otherwise, the previous valid content is retained.

        Returns:
            Tuple of:
                final_content
                reflection_logs
        """

        logger.info(
            "Initiating Reflection / Self-Check audit phase..."
        )

        if not content or not content.strip():
            raise ReflectionException(
                "Reflection cannot operate on empty document content."
            )

        # --------------------------------------------------------------
        # Establish the original document as the safe baseline.
        # --------------------------------------------------------------

        current_content = content.strip()

        baseline_metrics = self._document_metrics(
            current_content
        )

        logger.info(
            "Reflection baseline: "
            f"{baseline_metrics['words']} words, "
            f"{baseline_metrics['characters']} characters, "
            f"{baseline_metrics['headings']} headings."
        )

        if baseline_metrics["words"] < self.MIN_DOCUMENT_WORDS:
            logger.warning(
                "Document is already shorter than the recommended "
                f"{self.MIN_DOCUMENT_WORDS} words before reflection."
            )

        reflection_logs: List[str] = []

        assumptions_str = (
            "\n".join(
                f"- {assumption}"
                for assumption in assumptions
            )
            if assumptions
            else "None"
        )

        # --------------------------------------------------------------
        # Reflection loop
        # --------------------------------------------------------------

        for loop in range(
            1,
            max_reflection_loops + 1,
        ):

            logger.info(
                f"Reflection cycle "
                f"{loop}/{max_reflection_loops}"
            )

            current_metrics = self._document_metrics(
                current_content
            )

            # ----------------------------------------------------------
            # Build audit prompt
            # ----------------------------------------------------------

            prompt = f"""
You are the final Quality Assurance Auditor for a professional
business document.

Your job is to inspect the document and determine whether it is
complete, coherent, professional, internally consistent and ready
for delivery.

DOCUMENT TYPE:
{document_type}

ORIGINAL USER REQUEST:
{request}

KNOWN ASSUMPTIONS:
{assumptions_str}

CURRENT DOCUMENT:
{current_content}

============================================================
AUDIT OBJECTIVES
============================================================

Check the document for:

1. Completeness
2. Missing sections
3. Missing requirements from the original request
4. Logical consistency
5. Contradictory numbers
6. Budget consistency
7. Timeline consistency
8. Professional tone
9. Grammar
10. Formatting
11. Placeholder text
12. Unsupported claims
13. Repetition
14. Truncation
15. Incomplete sentences
16. Missing conclusions
17. Missing assumptions
18. Broken Markdown tables

============================================================
CRITICAL CONTENT-PRESERVATION RULE
============================================================

The document is already a multi-step generated artifact.

DO NOT shorten it merely to make it cleaner.

DO NOT summarize it.

DO NOT remove substantive sections.

DO NOT remove important details.

DO NOT replace detailed sections with short summaries.

If the document is already complete and professional, approve it.

If corrections are required, the complete document must be preserved.

============================================================
TRUNCATION DETECTION
============================================================

Pay particular attention to whether the document appears to start
in the middle of a larger document.

For example, if the document begins with:

"7. Risk Management"

without Sections 1-6 being present, consider that a completeness
failure.

Likewise, detect:

- sudden ending
- incomplete sentences
- unfinished tables
- missing conclusions
- abrupt section transitions
- headings that appear to reference earlier missing sections

============================================================
OUTPUT
============================================================

Return valid JSON with exactly these fields:

{{
    "approved": true or false,
    "feedback": "Detailed audit findings",
    "improved_content": "Complete corrected document if changes are required, otherwise null"
}}

IMPORTANT:

If approved is true:

"improved_content" MUST be null.

If approved is false:

"improved_content" MUST contain the COMPLETE document.

Do NOT return only the corrected section.

Do NOT return a summary.

Do NOT return a partial document.

Return valid JSON only.
"""

            try:

                # ------------------------------------------------------
                # Call auditor
                # ------------------------------------------------------

                raw_response = self.client.generate(
                    prompt=prompt,
                    system_prompt=(
                        "You are a strict, detail-oriented "
                        "Quality Assurance Auditor. "
                        "Preserve document content."
                    ),
                    response_format="json",
                )

                # ------------------------------------------------------
                # Parse structured result
                # ------------------------------------------------------

                audit_result = (
                    ReflectionOutput.model_validate_json(
                        raw_response
                    )
                )

                log_entry = (
                    f"Cycle {loop} - "
                    f"Approved: {audit_result.approved}. "
                    f"Auditor Feedback: "
                    f"{audit_result.feedback}"
                )

                logger.info(log_entry)

                reflection_logs.append(
                    log_entry
                )

                # ------------------------------------------------------
                # APPROVED
                # ------------------------------------------------------

                if audit_result.approved:

                    logger.info(
                        "Document successfully approved "
                        "by Reflection agent."
                    )

                    return (
                        current_content,
                        reflection_logs,
                    )

                # ------------------------------------------------------
                # REJECTED WITHOUT REVISION
                # ------------------------------------------------------

                if not audit_result.improved_content:

                    logger.warning(
                        "Reflection rejected the document but "
                        "did not provide improved content."
                    )

                    # Important:
                    # Do not destroy the existing valid document.
                    reflection_logs.append(
                        "Revision unavailable. "
                        "Retained previous valid document."
                    )

                    return (
                        current_content,
                        reflection_logs,
                    )

                proposed_content = (
                    audit_result.improved_content.strip()
                )

                # ------------------------------------------------------
                # Validate proposed revision
                # ------------------------------------------------------

                is_valid, validation_reason = (
                    self._validate_revision(
                        original=current_content,
                        proposed=proposed_content,
                    )
                )

                if not is_valid:

                    logger.warning(
                        "Reflection revision rejected: "
                        f"{validation_reason}"
                    )

                    reflection_logs.append(
                        "Proposed reflection revision rejected: "
                        f"{validation_reason}. "
                        "Previous document retained."
                    )

                    # CRITICAL:
                    # Never replace a good document with a suspicious
                    # shortened/truncated reflection response.
                    return (
                        current_content,
                        reflection_logs,
                    )

                # ------------------------------------------------------
                # Accept safe revision
                # ------------------------------------------------------

                logger.info(
                    "Reflection revision passed safety validation."
                )

                logger.info(
                    "Revision size: "
                    f"{len(proposed_content)} characters / "
                    f"{len(proposed_content.split())} words."
                )

                current_content = proposed_content

            # ----------------------------------------------------------
            # JSON error
            # ----------------------------------------------------------

            except json.JSONDecodeError as error:

                logger.error(
                    "Reflection output was not valid JSON: "
                    f"{error}"
                )

                # Do not destroy the document because the auditor's
                # response was malformed.
                reflection_logs.append(
                    "Reflection returned malformed JSON. "
                    "Previous valid document retained."
                )

                return (
                    current_content,
                    reflection_logs,
                )

            # ----------------------------------------------------------
            # Reflection-specific error
            # ----------------------------------------------------------

            except ReflectionException:

                raise

            # ----------------------------------------------------------
            # Unexpected error
            # ----------------------------------------------------------

            except Exception as error:

                logger.error(
                    f"Error during reflection analysis: {error}"
                )

                reflection_logs.append(
                    f"Reflection error: {error}. "
                    "Previous valid document retained."
                )

                return (
                    current_content,
                    reflection_logs,
                )

        # --------------------------------------------------------------
        # Maximum reflection cycles reached
        # --------------------------------------------------------------

        logger.info(
            f"Reached maximum reflection loops "
            f"({max_reflection_loops}). "
            "Returning latest validated document."
        )

        return (
            current_content,
            reflection_logs,
        )

    # ==================================================================
    # REVISION VALIDATION
    # ==================================================================

    def _validate_revision(
        self,
        original: str,
        proposed: str,
    ) -> tuple[bool, str]:
        """
        Validate an LLM-generated revision before accepting it.

        This is an important engineering safeguard because an LLM can
        produce a valid-looking response that is actually much shorter
        or incomplete.
        """

        if not proposed:
            return (
                False,
                "Proposed revision is empty.",
            )

        original_metrics = self._document_metrics(
            original
        )

        proposed_metrics = self._document_metrics(
            proposed
        )

        logger.info(
            "Comparing original and reflection revision:"
        )

        logger.info(
            f"Original: "
            f"{original_metrics['words']} words, "
            f"{original_metrics['headings']} headings."
        )

        logger.info(
            f"Proposed: "
            f"{proposed_metrics['words']} words, "
            f"{proposed_metrics['headings']} headings."
        )

        # --------------------------------------------------------------
        # Minimum content
        # --------------------------------------------------------------

        if proposed_metrics["words"] < self.MIN_DOCUMENT_WORDS:

            return (
                False,
                "Proposed document is too short."
            )

        # --------------------------------------------------------------
        # Retention ratio
        # --------------------------------------------------------------

        if original_metrics["words"] > 0:

            retention_ratio = (
                proposed_metrics["words"]
                / original_metrics["words"]
            )

            logger.info(
                f"Reflection content retention ratio: "
                f"{retention_ratio:.2f}"
            )

            if retention_ratio < self.MIN_RETENTION_RATIO:

                return (
                    False,
                    (
                        "Proposed revision is substantially shorter "
                        f"than original "
                        f"({retention_ratio:.0%} retained)."
                    ),
                )

        # --------------------------------------------------------------
        # Heading retention
        # --------------------------------------------------------------

        original_headings = self._extract_headings(
            original
        )

        proposed_headings = self._extract_headings(
            proposed
        )

        if len(original_headings) >= 3:

            missing_headings = [
                heading
                for heading in original_headings
                if not self._heading_exists(
                    heading,
                    proposed_headings,
                )
            ]

            # Don't allow a revision to lose a large portion of the
            # original structure.
            allowed_missing = max(
                1,
                len(original_headings) // 4,
            )

            if len(missing_headings) > allowed_missing:

                return (
                    False,
                    (
                        "Proposed revision loses too many document "
                        f"sections. Missing approximately "
                        f"{len(missing_headings)} headings."
                    ),
                )

        # --------------------------------------------------------------
        # Placeholder detection
        # --------------------------------------------------------------

        placeholders = (
            self._find_placeholders(proposed)
        )

        if placeholders:

            return (
                False,
                (
                    "Proposed revision contains placeholders: "
                    + ", ".join(placeholders[:5])
                ),
            )

        # --------------------------------------------------------------
        # Truncation detection
        # --------------------------------------------------------------

        if self._looks_truncated(proposed):

            return (
                False,
                "Proposed revision appears truncated."
            )

        # --------------------------------------------------------------
        # Suspicious section start
        # --------------------------------------------------------------

        if self._starts_mid_document(proposed):

            return (
                False,
                (
                    "Proposed revision appears to start in the middle "
                    "of the document."
                ),
            )

        return True, "Revision passed validation."

    # ==================================================================
    # DOCUMENT METRICS
    # ==================================================================

    def _document_metrics(
        self,
        content: str,
    ) -> dict:
        """
        Calculate basic structural metrics.
        """

        words = len(
            content.split()
        )

        characters = len(
            content
        )

        headings = len(
            self._extract_headings(content)
        )

        tables = len(
            re.findall(
                r"^\s*\|.*\|\s*$",
                content,
                flags=re.MULTILINE,
            )
        )

        return {
            "words": words,
            "characters": characters,
            "headings": headings,
            "tables": tables,
        }

    # ==================================================================
    # HEADING UTILITIES
    # ==================================================================

    def _extract_headings(
        self,
        content: str,
    ) -> List[str]:
        """
        Extract Markdown headings.
        """

        headings = []

        for line in content.splitlines():

            match = re.match(
                r"^\s*#{1,6}\s+(.+?)\s*$",
                line,
            )

            if match:

                heading = match.group(1).strip()

                if heading:
                    headings.append(
                        heading
                    )

        return headings

    def _heading_exists(
        self,
        heading: str,
        headings: List[str],
    ) -> bool:
        """
        Fuzzy heading comparison.
        """

        normalized = self._normalize_text(
            heading
        )

        for candidate in headings:

            candidate_normalized = (
                self._normalize_text(candidate)
            )

            if (
                normalized == candidate_normalized
                or normalized in candidate_normalized
                or candidate_normalized in normalized
            ):
                return True

        return False

    def _normalize_text(
        self,
        value: str,
    ) -> str:
        """
        Normalize text for structural comparison.
        """

        value = value.lower()

        value = re.sub(
            r"[^a-z0-9\s]",
            " ",
            value,
        )

        value = re.sub(
            r"\s+",
            " ",
            value,
        )

        return value.strip()

    # ==================================================================
    # PLACEHOLDER DETECTION
    # ==================================================================

    def _find_placeholders(
        self,
        content: str,
    ) -> List[str]:
        """
        Detect common unresolved placeholders.
        """

        found: List[str] = []

        for pattern in self.PLACEHOLDER_PATTERNS:

            matches = re.findall(
                pattern,
                content,
                flags=re.IGNORECASE,
            )

            found.extend(matches)

        return list(
            dict.fromkeys(found)
        )

    # ==================================================================
    # TRUNCATION DETECTION
    # ==================================================================

    def _looks_truncated(
        self,
        content: str,
    ) -> bool:
        """
        Detect obvious signs of incomplete LLM output.
        """

        stripped = content.strip()

        if not stripped:
            return True

        # Common LLM truncation indicators.
        truncation_patterns = [
            r"\.\.\.$",
            r"…$",
            r":$",
            r"[,;]$",
        ]

        for pattern in truncation_patterns:

            if re.search(
                pattern,
                stripped,
            ):
                # A colon/comma at the end isn't always truncation,
                # so only treat it as suspicious for longer documents.
                if len(stripped) > 2000:
                    return True

        # Check for unbalanced Markdown fences.
        if stripped.count("```") % 2 != 0:
            return True

        return False

    # ==================================================================
    # MID-DOCUMENT START DETECTION
    # ==================================================================

    def _starts_mid_document(
        self,
        content: str,
    ) -> bool:
        """
        Detect documents that appear to begin with a later numbered
        section such as "7. Risk Management".

        This specifically protects against the type of incomplete
        document produced previously.
        """

        lines = [
            line.strip()
            for line in content.splitlines()
            if line.strip()
        ]

        if not lines:
            return True

        first_line = lines[0]

        # Examples:
        # 7. Risk Management
        # ## 7. Risk Management
        # 7 Risk Management

        match = re.match(
            r"^(?:#+\s*)?(\d+)[.)]\s+.+$",
            first_line,
        )

        if match:

            section_number = int(
                match.group(1)
            )

            # A document beginning with Section 2 or later is suspicious.
            if section_number > 1:

                logger.warning(
                    "Document appears to start at section "
                    f"{section_number}."
                )

                return True

        return False