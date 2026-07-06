"""
Reflection / Self-Check Module for the Autonomous Business Document Agent.

This module acts as an autonomous auditor. It takes the compiled document draft
and reviews it against quality criteria (grammar, tone, completeness, formatting,
logical consistency). If issues are found, it instructs the LLM to rewrite and improve
the content, acting as a critical feedback loop.

================================================================================
ENGINEERING RATIONALE: WHY REFLECTION IMPROVES AUTONOMOUS REASONING
================================================================================
1. Open-Loop vs. Closed-Loop Execution:
   Without reflection, an agent operates in an 'open-loop' mode, outputting the first
   draft it produces. Reflection closes this loop, ensuring the agent evaluates its
   own outputs before declaring success. This is essential for interview-ready,
   production-grade systems.
2. Task Specialization (Creative vs. Critical Personas):
   LLMs perform better when instructed to focus on one cognitive style. During content
   generation, the model acts creatively. During reflection, the model transitions into a
   strict, critical auditor. This prevents typical generation artifacts (like placeholders,
   e.g. '[Insert Budget Here]', 'TODO') from leaking into the final output.
3. Global Context Review:
   Since the document is generated section-by-section (to prevent context limits or formatting
   loss), local contradictions may arise (e.g. Budget is $15k in Section 1, but $12k in Section 3).
   The Reflection module reviews the document as a single unified piece to enforce global consistency.
================================================================================
"""

import json
from typing import List
from llm import GeminiClient
from models import ReflectionOutput
from prompts import REFLECTION_SYSTEM_PROMPT
from utils import ReflectionException, logger


class ReflectionAgent:
    """
    ReflectionAgent audits generated text for quality issues and automatically rewrites
    the content if it fails to meet the defined professional standards.
    """

    def __init__(self, client: GeminiClient | None = None) -> None:
        """
        Initializes the ReflectionAgent with a Gemini client.
        """
        self.client = client or GeminiClient()

    def reflect_and_improve(
        self,
        request: str,
        document_type: str,
        assumptions: List[str],
        content: str,
        max_reflection_loops: int = 1,
    ) -> tuple[str, List[str]]:
        """
        Audits and refines the draft document content.

        Args:
            request: The user's original request.
            document_type: The category of document generated.
            assumptions: Assumptions formulated during the project.
            content: The compiled draft document content.
            max_reflection_loops: The maximum allowed self-correction cycles (default: 1).

        Returns:
            A tuple of (final_content, reflection_logs) where final_content is either the
            original or the improved version, and reflection_logs records the audit notes.

        Raises:
            ReflectionException: If the reflection validation fails.
        """
        logger.info("Initiating Reflection / Self-Check audit phase...")
        current_content = content
        reflection_logs = []

        assumptions_str = (
            "\n".join(f"- {a}" for a in assumptions) if assumptions else "None"
        )

        for loop in range(1, max_reflection_loops + 1):
            logger.info(f"Reflection cycle {loop}/{max_reflection_loops}")

            # Formulate audit prompt
            prompt = REFLECTION_SYSTEM_PROMPT.format(
                request=request,
                document_type=document_type,
                assumptions=assumptions_str,
                document_content=current_content,
            )

            try:
                # Call LLM with JSON format requirement
                raw_response = self.client.generate(
                    prompt=prompt,
                    system_prompt="You are a strict, detail-oriented Quality Assurance Auditor.",
                    response_format="json",
                )

                # Parse and validate the auditor's structured critique
                audit_result = ReflectionOutput.model_validate_json(raw_response)

                log_entry = (
                    f"Cycle {loop} - Approved: {audit_result.approved}. "
                    f"Auditor Feedback: {audit_result.feedback}"
                )
                logger.info(log_entry)
                reflection_logs.append(log_entry)

                if audit_result.approved:
                    logger.info("Document successfully approved by Reflection agent.")
                    # Return original or current content if approved
                    return current_content, reflection_logs

                # If rejected, update content with the improved version
                if not audit_result.improved_content:
                    raise ReflectionException(
                        "Reflection agent rejected the document but failed to provide improved content."
                    )

                logger.info(
                    f"Reflection cycle {loop} requested corrections. Replacing content with improved revision."
                )
                current_content = audit_result.improved_content

            except json.JSONDecodeError as jde:
                logger.error(f"Reflection output was not valid JSON: {jde}")
                raise ReflectionException(
                    "Reflection failed to return structured JSON critique.",
                    details=str(jde),
                ) from jde

            except Exception as err:
                if isinstance(err, ReflectionException):
                    raise err
                logger.error(f"Error during reflection analysis: {err}")
                raise ReflectionException(
                    "Document reflection step failed.", details=str(err)
                ) from err

        logger.warning(
            f"Reached max reflection loops ({max_reflection_loops}) without explicit audit approval. "
            "Returning latest revised content."
        )
        return current_content, reflection_logs
