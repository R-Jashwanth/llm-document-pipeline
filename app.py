"""
FastAPI Server Application Module.

This is the presentation and entry point layer for the Autonomous Document Agent.
It exposes a single POST /agent endpoint to receive document requests, performs input validation,
configures logging, and translates internal exceptions into structured JSON error responses.

Design Decisions:
1. Unified Exception Translation: Registers global exception handlers for internal AgentException
   and standard Pydantic RequestValidationError. This guarantees that all client errors,
   runtime LLM issues, and system failures always return structured JSON with 'status': 'error'.
2. Fail-Safe Gateway: Halts server boot if the configurations are invalid (config.py is loaded on import).
3. Logging Middleware: Logs incoming request paths, response times, and failure reports.
"""

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from agent import AutonomousAgent
from config import settings
from models import AgentRequest, AgentResponse
from utils import AgentException, logger

# Initialize FastAPI App metadata
app = FastAPI(
    title="Autonomous Business Document Agent API",
    description=(
        "FastAPI service exposing an autonomous agent pipeline that plans, "
        "drafts, audits (reflects), and compiles professional Word documents (.docx)."
    ),
    version="1.0.0",
)

# Instantiate the coordinating agent singleton on startup
agent = AutonomousAgent()


@app.on_event("startup")
async def startup_event() -> None:
    """
    Logs application startup parameters.
    """
    logger.info("================================================================")
    logger.info("Autonomous Document Agent API Server is boot-starting.")
    logger.info(f"Environment : {settings.environment.upper()}")
    logger.info(f"Uvicorn Host: {settings.host}:{settings.port}")
    logger.info(f"Output Path : {settings.generated_dir.resolve()}")
    logger.info("================================================================")


# ==============================================================================
# Structured Exception Handlers
# ==============================================================================
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request, exc: RequestValidationError
) -> JSONResponse:
    """
    Catches client input validation failures (e.g. empty or short request fields)
    and formatting issues, translating them into structured error responses.
    """
    logger.warning(f"Gateway rejected request validation: {exc}")
    errors = exc.errors()

    # Formulate human-readable error descriptions
    error_list = []
    for err in errors:
        location = ".".join(str(loc_item) for loc_item in err.get("loc", []))
        message = err.get("msg", "Unknown validation issue")
        error_list.append(f"[{location}]: {message}")

    joined_details = "; ".join(error_list)

    return JSONResponse(
        status_code=422,
        content={
            "status": "error",
            "error_type": "ValidationError",
            "message": "The input request did not pass schema validation checks.",
            "details": joined_details,
        },
    )


@app.exception_handler(AgentException)
async def agent_exception_handler(request, exc: AgentException) -> JSONResponse:
    """
    Translates internal domain exception sub-classes (LLMException, PlannerException,
    ExecutorException, ReflectionException, DocxException) into detailed HTTP 400 responses.
    """
    logger.error(
        f"Pipeline Exception [{exc.__class__.__name__}]: {exc.message} | Details: {exc.details}"
    )
    return JSONResponse(
        status_code=400,
        content={
            "status": "error",
            "error_type": exc.__class__.__name__,
            "message": exc.message,
            "details": exc.details or "No additional trace details provided.",
        },
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request, exc: Exception) -> JSONResponse:
    """
    Catches raw, unexpected exceptions and wraps them to avoid exposing
    raw system traces, returning standard HTTP 500.
    """
    logger.critical(f"Critical unhandled exception caught: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "status": "error",
            "error_type": "InternalServerError",
            "message": "An unexpected critical server error occurred.",
            "details": str(exc),
        },
    )


# ==============================================================================
# Endpoint Routers
# ==============================================================================
@app.post(
    "/agent",
    response_model=AgentResponse,
    summary="Generate Business Document",
    description=(
        "Triggers the autonomous document compilation loop. Plans structure, "
        "executes section writing, audits content (reflection), compiles a .docx file, "
        "and returns execution metadata."
    ),
)
async def run_agent(payload: AgentRequest) -> AgentResponse:
    """
    Receives request payload, routes it to the orchestrator agent, and returns response.
    """
    logger.info(f"API route received generate request. Query: '{payload.request[:60]}...'")
    response = agent.process_request(payload.request)
    return response
