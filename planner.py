"""
Planner Module for the Autonomous Business Document Agent.

This module is responsible for analyzing the natural language request, classifying
it into a standard document type, mapping out any necessary assumptions for missing
information, and compiling a sequence of structured execution steps (tasks)
that mapping to actions in the Tool Registry.

Design Decisions:
1. Separation of Concerns: The planner is strictly metadata-focused. It classifies
   and schedules, but never generates document content directly.
2. Structured Schema Enforcement: The planner uses Gemini's JSON response format
   coupled with Pydantic's model_validate_json() validation. If the LLM generates
   invalid task actions or formatting, the Planner raises a PlannerException to fail-fast.
3. Extensible Task Mapping: Task objects associate a specific action string (like 'generate_outline')
   with a description, allowing the Executor module to invoke these tools dynamically.
"""

import json
from llm import GeminiClient
from models import PlannerPlan
from prompts import PLANNER_SYSTEM_PROMPT, PLANNER_USER_PROMPT_TEMPLATE
from utils import PlannerException, logger


class PlannerAgent:
    """
    PlannerAgent decomposes natural language requests into structured execution paths.
    It determines the document type, lists assumptions, and returns a checklist of tasks.
    """

    def __init__(self, client: GeminiClient | None = None) -> None:
        """
        Initializes the PlannerAgent with a GeminiClient.
        """
        self.client = client or GeminiClient()

    def generate_plan(self, request: str) -> PlannerPlan:
        """
        Analyzes the request and returns a structured PlannerPlan.

        Args:
            request: The user's natural language request.

        Returns:
            A PlannerPlan object containing the document type, assumptions, and tasks list.

        Raises:
            PlannerException: If the planner is unable to generate or validate the plan.
        """
        logger.info(f"Generating plan for request: '{request[:60]}...'")

        # Format user prompt
        user_prompt = PLANNER_USER_PROMPT_TEMPLATE.format(request=request)

        try:
            # Request strict JSON response from the LLM client
            raw_response = self.client.generate(
                prompt=user_prompt,
                system_prompt=PLANNER_SYSTEM_PROMPT,
                response_format="json",
            )

            # Parse and validate against the Pydantic schema
            plan = PlannerPlan.model_validate_json(raw_response)

            logger.info(
                f"Successfully planned document generation: Inferred type='{plan.document_type}', "
                f"Tasks={len(plan.tasks)}, Assumptions={len(plan.assumptions)}"
            )

            # Extra safety check: verify tasks list is not empty
            if not plan.tasks:
                raise PlannerException(
                    "Planner generated an empty task checklist."
                )

            # Verify that actions are correct
            valid_actions = {"generate_outline", "generate_section", "refine_content"}
            for idx, task in enumerate(plan.tasks):
                if task.action not in valid_actions:
                    raise PlannerException(
                        f"Planner generated an invalid task action '{task.action}' at index {idx}. "
                        f"Must be one of {valid_actions}."
                    )

            return plan

        except json.JSONDecodeError as jde:
            logger.error(f"Planner response was not valid JSON: {jde}")
            raise PlannerException(
                "Planner failed to return structured plan JSON.", details=str(jde)
            ) from jde

        except Exception as err:
            if isinstance(err, PlannerException):
                raise err
            logger.error(f"Failed to generate execution plan: {err}")
            raise PlannerException(
                "Execution plan generation failed.", details=str(err)
            ) from err
