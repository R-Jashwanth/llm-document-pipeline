"""
Business Document Content Generator Module.

This module implements the content creation tools registered in the executor's Tool Registry.
It leverages Google Gemini 2.5 Flash through the standardized GeminiClient interface
to produce outlines, write detailed sections chronologically (maintaining context),
and compile draft sections into a polished, unified markdown document.

Design Decisions:
1. Tool-Based Design: Standardizes handlers to take (ExecutorState, Task) as arguments
   and return the generated string. This interface aligns with the dynamic Tool Registry.
2. Contextual Writing: When writing subsequent sections, the generator extracts previous
   completed sections from the task state history, preventing repetition and keeping content cohesive.
3. Cohesive Refinement: The refiner step cleans formatting, heading hierachies, and merges
   disparate sections into a singular high-quality document ready for the Reflection phase.
"""

from llm import GeminiClient
from models import ExecutorState, Task
from prompts import (
    OUTLINE_SYSTEM_PROMPT,
    REFINER_SYSTEM_PROMPT,
    SECTION_GENERATOR_SYSTEM_PROMPT,
)
from utils import ExecutorException, logger


class DocumentGenerator:
    """
    DocumentGenerator contains implementation functions for document creation tasks.
    These methods are mapped directly within the executor's tool registry.
    """

    def __init__(self, client: GeminiClient | None = None) -> None:
        """
        Initializes the generator with a Gemini client.
        """
        self.client = client or GeminiClient()

    def generate_outline(self, state: ExecutorState, task: Task) -> str:
        """
        Generates the hierarchical skeleton/outline for the document.
        Invoked as the first step in the generation workflow.
        """
        logger.info(
            f"Executing tool 'generate_outline' for Document Type: {state.document_type}"
        )

        assumptions_str = (
            "\n".join(f"- {a}" for a in state.assumptions)
            if state.assumptions
            else "None"
        )

        prompt = OUTLINE_SYSTEM_PROMPT.format(
            document_type=state.document_type,
            request=state.original_request,
            assumptions=assumptions_str,
        )

        outline = self.client.generate(prompt=prompt, response_format="text")
        logger.info("Document outline generated successfully.")
        return outline

    def generate_section(self, state: ExecutorState, task: Task) -> str:
        """
        Writes the prose for a single section.
        Retrieves the outline and previous sections to maintain context and style.
        """
        logger.info(f"Executing tool 'generate_section' for: '{task.description}'")

        # 1. Retrieve the outline from state history
        outline = ""
        for t in state.tasks:
            if t.action == "generate_outline" and t.status == "completed":
                outline = t.output or ""
                break

        if not outline:
            logger.warning(
                "Outline not found in state history. Proceeding without outline context."
            )

        # 2. Extract only the LAST completed section to maintain continuity without overflow
        previous_sections = []
        for t in state.tasks:
            if (
                t.action == "generate_section"
                and t.status == "completed"
                and t.output
            ):
                previous_sections.append(
                    f"### Section: {t.description}\n{t.output}"
                )

        # Only keep the last section to avoid context window overflow
        if previous_sections:
            last_section = previous_sections[-1]
            # Trim to 800 chars max to stay within token limits
            if len(last_section) > 800:
                last_section = last_section[:800] + "..."
            previous_content_str = last_section
        else:
            previous_content_str = "None yet."

        # 3. Format assumptions
        assumptions_str = (
            "\n".join(f"- {a}" for a in state.assumptions)
            if state.assumptions
            else "None"
        )

        # 4. Generate content utilizing context
        prompt = SECTION_GENERATOR_SYSTEM_PROMPT.format(
            document_type=state.document_type,
            request=state.original_request,
            outline=outline,
            assumptions=assumptions_str,
            previous_content=previous_content_str,
            section_name=task.description,
            section_description=task.description,
        )

        section_content = self.client.generate(prompt=prompt, response_format="text")
        logger.info(f"Completed writing section: '{task.description}'")
        return section_content

    def refine_content(self, state: ExecutorState, task: Task) -> str:
        """
        Aggregates all written sections, reviews formatting, removes duplication,
        and produces the complete, compiled markdown draft.
        """
        logger.info("Executing tool 'refine_content' to compile all draft sections.")

        # Collect content from all completed generate_section tasks
        sections_to_compile = []
        for t in state.tasks:
            if t.action == "generate_section" and t.output:
                sections_to_compile.append(
                    f"## Section: {t.description}\n\n{t.output}"
                )

        if not sections_to_compile:
            raise ExecutorException(
                "Cannot execute refiner: no draft sections found in state history."
            )

        draft_sections_str = "\n\n".join(sections_to_compile)
        assumptions_str = (
            "\n".join(f"- {a}" for a in state.assumptions)
            if state.assumptions
            else "None"
        )

        prompt = REFINER_SYSTEM_PROMPT.format(
            document_type=state.document_type,
            request=state.original_request,
            assumptions=assumptions_str,
            draft_sections=draft_sections_str,
        )

        refined_document = self.client.generate(prompt=prompt, response_format="text")
        logger.info("Document refinement and compilation complete.")
        return refined_document
