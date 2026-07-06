"""
Executor Module for the Autonomous Business Document Agent.

This module is responsible for orchestrating task execution in a sequential and
explainable manner. It maintains execution logs, tracks task statuses, manages intermediate
outputs, and coordinates the flow of state variables throughout the document generation lifecycle.

================================================================================
ENGINEERING RATIONALE: TOOL REGISTRY VS. HARDCODED IF/ELSE WORKFLOWS
================================================================================
1. Extensibility (Open-Closed Principle):
   A Tool Registry decouples the Executor's flow control from the actual task implementations.
   To add a new tool (e.g. "generate_chart" or "run_web_search"), we simply register a new handler
   mapping in the registry dictionary without modifying the core execution loop inside execute().
2. Readability & Code Quality:
   Removing massive nested if/else statements keeps the execute() loop small, clean,
   and easy to follow.
3. Testability / Mocking:
   Individual tools within the registry can be mocked or swapped out easily during
   unit testing or staging operations.
================================================================================
"""

from typing import Callable, Dict
from document_generator import DocumentGenerator
from models import ExecutorState, Task
from utils import ExecutorException, logger


class Executor:
    """
    Executor runs planned document tasks sequentially using a dynamic Tool Registry.
    Tracks state transitions and logs detailed process metrics for audit logging.
    """

    def __init__(self, doc_generator: DocumentGenerator | None = None) -> None:
        """
        Initializes the Executor and configures the Tool Registry.
        """
        self.generator = doc_generator or DocumentGenerator()

        # Dynamic Tool Registry mapping action strings to executable handler functions.
        # All registry handlers accept (ExecutorState, Task) and return generated content.
        self.tools: Dict[str, Callable[[ExecutorState, Task], str]] = {
            "generate_outline": self.generator.generate_outline,
            "generate_section": self.generator.generate_section,
            "refine_content": self.generator.refine_content,
        }

    def execute(self, state: ExecutorState) -> ExecutorState:
        """
        Loops through all planned tasks in the state, looks up their handler in the
        Tool Registry, updates the running status, and collects intermediate logs.

        Args:
            state: The current running ExecutorState.

        Returns:
            The fully updated ExecutorState containing final logs and aggregated text.

        Raises:
            ExecutorException: If any task fails or references an unregistered action.
        """
        logger.info(
            f"Beginning sequential execution of {len(state.tasks)} plan tasks."
        )

        for index, task in enumerate(state.tasks, start=1):
            if task.status == "completed":
                logger.info(
                    f"Task {index}/{len(state.tasks)}: '{task.description}' is already completed. Skipping."
                )
                continue

            logger.info(
                f"Task {index}/{len(state.tasks)}: Starting '{task.description}' [Action: {task.action}]"
            )

            # Transition task status to active running state
            task.status = "running"
            state.logs.append(
                f"Task {index}/{len(state.tasks)}: Started '{task.description}' ({task.action})"
            )

            try:
                # Retrieve registered handler from the Tool Registry
                if task.action not in self.tools:
                    raise ExecutorException(
                        f"Unregistered action '{task.action}' requested by planner plan."
                    )

                handler = self.tools[task.action]

                # Invoke the tool handler
                output_content = handler(state, task)

                # Store intermediate output and finalize task status
                task.output = output_content
                task.status = "completed"

                # Update the main content block if this is the final aggregation/refinement
                if task.action == "refine_content":
                    state.document_content = output_content

                log_success = (
                    f"Task {index}/{len(state.tasks)}: Completed successfully."
                )
                logger.info(log_success)
                state.logs.append(log_success)

            except Exception as e:
                task.status = "failed"
                log_error = f"Task {index}/{len(state.tasks)}: Failed with error: {e}"
                logger.error(log_error)
                state.logs.append(log_error)

                # Wrap and re-raise to fail-fast the execution run
                raise ExecutorException(
                    f"Failed executing task '{task.description}': {e}",
                    details=str(e),
                ) from e

        logger.info("Document compilation tasks successfully completed.")
        return state
