"""
Autonomous Business Document Agent Orchestrator.

Coordinates the complete autonomous document-generation workflow:

    Request
       ↓
    Planner
       ↓
    Executor
       ↓
    Reflection / Self-check
       ↓
    DOCX Compiler
       ↓
    API Response
"""

from docx_generator import DocxGenerator
from document_generator import DocumentGenerator
from executor import Executor
from llm import GeminiClient
from models import AgentResponse, ExecutorState
from planner import PlannerAgent
from reflection import ReflectionAgent
from utils import AgentException, execution_timer, logger


class AutonomousAgent:
    """
    Coordinates the end-to-end autonomous document-generation pipeline.
    """

    def __init__(self) -> None:
        """
        Initialize all agent components.

        A single LLM client is shared by Planner, Executor and Reflection
        components so that provider configuration and fallback behavior
        remain consistent across the entire pipeline.
        """

        self.client = GeminiClient()

        self.planner = PlannerAgent(self.client)

        # IMPORTANT:
        # Share the same LLM client with the executor instead of creating
        # another DocumentGenerator with its own client.
        self.document_generator = DocumentGenerator(self.client)

        self.executor = Executor(
            doc_generator=self.document_generator
        )

        self.reflection_agent = ReflectionAgent(self.client)

        self.docx_compiler = DocxGenerator()

    def process_request(self, request: str) -> AgentResponse:
        """
        Execute the complete autonomous document-generation pipeline.

        Steps:
        1. Generate an execution plan.
        2. Execute every planned task.
        3. Run reflection/self-check.
        4. Compile the final Markdown into DOCX.
        5. Return execution metadata and file information.
        """

        logger.info(
            "Autonomous Agent received document generation request: "
            f"'{request}'"
        )

        with execution_timer() as timer:

            try:

                # ======================================================
                # 1. PLAN
                # ======================================================

                logger.info("========== PLAN STAGE ==========")

                plan = self.planner.generate_plan(request)

                logger.info(
                    f"Planner selected document type: "
                    f"{plan.document_type}"
                )

                logger.info(
                    f"Planner created {len(plan.tasks)} tasks."
                )

                for index, task in enumerate(
                    plan.tasks,
                    start=1,
                ):
                    logger.info(
                        f"Plan Task {index}: "
                        f"{task.action} -> {task.description}"
                    )

                # ======================================================
                # 2. INITIALIZE STATE
                # ======================================================

                state = ExecutorState(
                    original_request=request,
                    document_type=plan.document_type,
                    tasks=plan.tasks,
                    assumptions=plan.assumptions,
                )

                # ======================================================
                # 3. EXECUTE
                # ======================================================

                logger.info("========== EXECUTION STAGE ==========")

                executed_state = self.executor.execute(state)

                logger.info(
                    "Executor completed successfully."
                )

                # Diagnostic logging: inspect every generated section.
                for index, task in enumerate(
                    executed_state.tasks,
                    start=1,
                ):
                    output_length = (
                        len(task.output)
                        if task.output
                        else 0
                    )

                    logger.info(
                        f"Task {index}: "
                        f"{task.action} | "
                        f"status={task.status} | "
                        f"output={output_length} chars"
                    )

                logger.info(
                    "Aggregated document content length before reflection: "
                    f"{len(executed_state.document_content)} characters"
                )

                # ======================================================
                # 4. REFLECTION
                # ======================================================

                logger.info("========== REFLECTION STAGE ==========")

                final_content, reflection_logs = (
                    self.reflection_agent.reflect_and_improve(
                        request=request,
                        document_type=executed_state.document_type,
                        assumptions=executed_state.assumptions,
                        content=executed_state.document_content,
                    )
                )

                if not final_content or not final_content.strip():
                    raise AgentException(
                        "Reflection returned empty final document."
                    )

                final_content = final_content.strip()

                logger.info(
                    "Reflection returned final content: "
                    f"{len(final_content)} characters"
                )

                logger.info(
                    f"Approximate final word count: "
                    f"{len(final_content.split())}"
                )

                # Update state.
                executed_state.document_content = final_content

                # ======================================================
                # 5. COMPILE DOCX
                # ======================================================

                logger.info("========== DOCX STAGE ==========")

                safe_name = (
                    executed_state.document_type
                    .lower()
                    .strip()
                    .replace(" ", "_")
                )

                filename = f"{safe_name}.docx"

                file_path = self.docx_compiler.create_docx(
                    markdown_content=final_content,
                    filename=filename,
                )

                logger.info(
                    f"DOCX generated successfully: {file_path}"
                )

                # ======================================================
                # 6. RESPONSE
                # ======================================================

                elapsed_seconds = timer["duration"]

                task_summaries = [
                    f"{task.description} -> [{task.status}]"
                    for task in executed_state.tasks
                ]

                word_count = len(
                    final_content.split()
                )

                summary = (
                    f"Successfully generated "
                    f"'{executed_state.document_type}' "
                    f"in {elapsed_seconds:.2f} seconds. "
                    f"Processed {len(executed_state.tasks)} pipeline tasks. "
                    f"Final document contains approximately "
                    f"{word_count} words. "
                    f"Self-checking audit executed "
                    f"{len(reflection_logs)} verification step(s)."
                )

                logger.info(
                    f"Orchestration pipeline succeeded: {summary}"
                )

                preview_length = 1000

                preview_text = (
                    final_content[:preview_length] + "..."
                    if len(final_content) > preview_length
                    else final_content
                )

                relative_file_path = (
                    f"generated/{filename}"
                )

                return AgentResponse(
                    status="success",
                    tasks=task_summaries,
                    assumptions=executed_state.assumptions,
                    document_type=executed_state.document_type,
                    generated_file=relative_file_path,
                    preview=preview_text,
                    execution_summary=summary,
                )

            except Exception as e:

                logger.error(
                    f"Pipeline execution halted due to error: {e}"
                )

                if isinstance(e, AgentException):
                    raise e

                raise AgentException(
                    "Autonomous document generation pipeline failed.",
                    details=str(e),
                ) from e