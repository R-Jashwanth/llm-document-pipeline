"""
Autonomous Business Document Agent Orchestrator.

This module is the core coordinator of the autonomous workflow. It binds
the Planner, Executor, ReflectionAgent, and DocxGenerator components into
a cohesive, sequential business document generation pipeline.

Design Decisions:
1. Orchestrator Pattern: The AutonomousAgent coordinates dependencies and manages the pipeline,
   while delegating detailed tasks to specialized sub-agents/modules. This keeps the codebase highly modular.
2. Complete State Profiling: An execution timer records metrics for the entire run. The final response
   contains the full checklist status, assumptions made, file paths, and detailed logs for transparency.
3. Fail-Safe Operations: If any component throws an exception, the orchestrator catches it, logs the failure,
   and propagates it gracefully for the API controller to respond with structured JSON error messages.
"""

from docx_generator import DocxGenerator
from executor import Executor
from llm import GeminiClient
from models import AgentResponse, ExecutorState
from planner import PlannerAgent
from reflection import ReflectionAgent
from utils import AgentException, execution_timer, logger


class AutonomousAgent:
    """
    AutonomousAgent coordinates the end-to-end processing pipeline for document generation.
    """

    def __init__(self) -> None:
        """
        Initializes orchestrator components.
        All modules share the same standardized GeminiClient instance to optimize connection pooling.
        """
        self.client = GeminiClient()
        self.planner = PlannerAgent(self.client)
        self.executor = Executor(None)
        self.reflection_agent = ReflectionAgent(self.client)
        self.docx_compiler = DocxGenerator()

    def process_request(self, request: str) -> AgentResponse:
        """
        Runs the full document generation agent loop:
        1. Classifies request and creates execution plan (Planner).
        2. Executes planned outline/section drafting sequentially (Executor).
        3. Audits draft content, correcting tone, grammar, and errors (Reflection).
        4. Compiles the audited draft into a professional .docx file (DocxGenerator).

        Args:
            request: The natural language request containing document guidelines.

        Returns:
            An AgentResponse containing execution plan details, assumptions, preview,
            and file destination path.

        Raises:
            AgentException: If any step in the pipeline fails.
        """
        logger.info(
            f"Autonomous Agent received document generation request: '{request}'"
        )

        with execution_timer() as timer:
            try:
                # 1. PLAN STAGE: Build the execution plan
                plan = self.planner.generate_plan(request)

                # Initialize state container
                state = ExecutorState(
                    original_request=request,
                    document_type=plan.document_type,
                    tasks=plan.tasks,
                    assumptions=plan.assumptions,
                )

                # 2. EXECUTE STAGE: Generate draft outline and write content sections
                executed_state = self.executor.execute(state)

                # 3. REFLECT STAGE: Quality assurance audit and self-correction rewrite
                final_content, reflection_logs = (
                    self.reflection_agent.reflect_and_improve(
                        request=request,
                        document_type=executed_state.document_type,
                        assumptions=executed_state.assumptions,
                        content=executed_state.document_content,
                    )
                )

                # Update state content with approved/revised version
                executed_state.document_content = final_content

                # 4. COMPILER STAGE: Compile markdown text to formatted MS Word Document
                safe_name = (
                    executed_state.document_type.lower().replace(" ", "_")
                )
                filename = f"{safe_name}.docx"

                file_path = self.docx_compiler.create_docx(
                    markdown_content=final_content, filename=filename
                )

                # Construct execution details
                elapsed_seconds = timer["duration"]
                task_summaries = [
                    f"{t.description} -> [{t.status}]"
                    for t in executed_state.tasks
                ]

                # Format human-readable runtime logs overview
                summary = (
                    f"Successfully generated '{executed_state.document_type}' in {elapsed_seconds:.2f} seconds. "
                    f"Processed {len(executed_state.tasks)} pipeline tasks. "
                    f"Self-checking audit executed {len(reflection_logs)} verification step(s)."
                )

                logger.info(f"Orchestration pipeline succeeded: {summary}")

                # Create preview text (first 500 characters)
                preview_length = 500
                preview_text = (
                    final_content[:preview_length] + "..."
                    if len(final_content) > preview_length
                    else final_content
                )

                # Map path relative to workspace or generated format
                relative_file_path = f"generated/{filename}"

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
                logger.error(f"Pipeline execution halted due to error: {e}")
                if isinstance(e, AgentException):
                    raise e
                raise AgentException(
                    "Autonomous document generation pipeline failed.",
                    details=str(e),
                ) from e
