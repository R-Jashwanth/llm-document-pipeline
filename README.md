# Autonomous Business Document Agent

A production-grade **Autonomous AI Agent** built with Python 3.11+, FastAPI, and a multi-provider LLM backend (Groq primary, Google Gemini fallback). The agent accepts a natural language request, automatically infers the target business document type, formulates an execution plan (checklist), executes each task sequentially (drafting the document section-by-section), performs a self-correcting reflection audit, and compiles a professionally formatted Microsoft Word (`.docx`) file.

---

## Architecture Diagram & Data Flow

```
                      +-----------------------------+
                      |      FastAPI Gateway        |
                      |          (app.py)           |
                      +--------------+--------------+
                                     |
                                     v
                      +-----------------------------+
                      |      Agent Orchestrator     |
                      |          (agent.py)         |
                      +-------+--------------+------+
                              |              ^
                              v              |
                      +-------+------+  +----+------+
                      |Planner Agent |  |Reflection |
                      | (planner.py) |  | (self-chk)|
                      +--------------+  +----+------+
                                             ^
                                             |
                      +----------------------+------+
                      |      Executor Engine        |
                      |  (utilizes Tool Registry)   |
                      +--------------+--------------+
                                     |
                                     v
                      +-----------------------------+
                      | Document Content Generator  |
                      |   (document_generator.py)   |
                      +--------------+--------------+
                                     |
                                     v
                      +-----------------------------+
                      |       DOCX Generator        |
                      |    (docx_generator.py)      |
                      +-----------------------------+
```

### Decoupled Data Flow
1. **API Entry**: FastAPI (`app.py`) validates incoming request text using Pydantic.
2. **Orchestration**: The `AutonomousAgent` (`agent.py`) handles state setup and times the pipeline.
3. **Planning Stage**: `PlannerAgent` (`planner.py`) analyzes the query, determines the document type, lists assumptions, and builds a list of tasks (represented by tool action names).
4. **Execution Stage**: `Executor` (`executor.py`) looks up each task action inside its extensible **Tool Registry** mapping, invoking the content generator (`document_generator.py`) to write the outline and prose sections contextually.
5. **Self-Correction (Reflection)**: `ReflectionAgent` (`reflection.py`) reviews the combined draft for quality (grammar, tone, completeness, formatting). If rejected, the LLM rewrites the document before validation completes.
6. **Word Compilation**: The approved content is passed to `DocxGenerator` (`docx_generator.py`) which translates Markdown headers, bold/italic text, tables, and lists into a native Microsoft Word (`.docx`) file.

---

## Folder Structure

```text
agent-assignment/
├── .env.example            # Environment variables configuration template
├── .gitignore              # Git ignore rules (excludes .env, generated/, __pycache__)
├── README.md               # Extensive project and interview documentation
├── agent.py                # Core coordinating agent orchestrator
├── app.py                  # FastAPI presentation layer & router
├── config.py               # Pydantic Settings configuration validator
├── document_generator.py   # Tool registry handlers (Outline, Section, Refiner)
├── docx_generator.py       # Markdown-to-DOCX compiler
├── executor.py             # Sequential task runner using Tool Registry
├── llm.py                  # Multi-provider LLM client (Groq primary, Gemini fallback)
├── models.py               # Pydantic request, response, and state models
├── prompts.py              # Central repository for LLM instructions & prompts
├── requirements.txt        # Stable third-party dependencies list
└── utils.py                # Logger configuration and custom exception classes
```

---

## Features

- **Decoupled Architecture (SOLID)**: Each class is designated a single responsiblity.
- **Dynamic Tool Registry**: Eliminates rigid `if/else` checks for task execution.
- **Reflection Feedback Loop**: Closes the execution loop, auditing drafts before saving.
- **Context-Preserved Document Generation**: Writes sections chronologically, pulling previously generated sections into the context window to prevent repetition.
- **Advanced Markdown-to-DOCX Parsing**: Compiles headers, bold/italic text runs, tables, and nested lists.
- **Strict Error Boundary**: Translates validation and pipeline errors into uniform JSON error payloads.

---

## Installation & Setup

1. **Clone or Navigate to the Directory**:
   ```bash
   git clone https://github.com/R-Jashwanth/llm-document-pipeline.git
   cd llm-document-pipeline
   ```

2. **Create and Activate a Virtual Environment** (Optional but Recommended):
   ```bash
   python -m venv venv
   # On Windows (Command Prompt)
   venv\Scripts\activate
   # On Windows (PowerShell)
   .\venv\Scripts\Activate.ps1
   ```

3. **Install Dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure Environment Variables**:
   Copy `.env.example` to `.env` and fill in your Gemini API key:
   ```bash
   copy .env.example .env
   ```
   Edit `.env`:
   ```env
   GEMINI_API_KEY=your_gemini_api_key_here
   GROQ_API_KEY=gsk_your_groq_key_here
   GEMINI_MODEL=gemini-2.0-flash
   HOST=127.0.0.1
   PORT=8000
   ENVIRONMENT=development
   LOG_LEVEL=INFO
   ```

   > **LLM Provider Notes:**
   > - `GROQ_API_KEY` is recommended — free tier at [console.groq.com](https://console.groq.com), no billing required, 14,400 req/day. The agent uses `llama-3.3-70b-versatile` for high-quality output.
   > - `GEMINI_API_KEY` is used as fallback. Get one from [aistudio.google.com](https://aistudio.google.com).
   > - If only Gemini is configured, the agent works Gemini-only.

---

## Running the Application

Start the FastAPI backend server using Uvicorn:
```bash
uvicorn app:app --reload
```

The API will start running at `http://127.0.0.1:8000`. You can access the auto-generated Swagger documentation at `http://127.0.0.1:8000/docs`.

---

## API Usage & Examples

### POST `/agent`

**Request Payload:**
```json
{
  "request": "Create a project proposal for implementing an AI chatbot in a hospital."
}
```

**cURL Command:**
```bash
curl -X POST http://127.0.0.1:8000/agent \
  -H "Content-Type: application/json" \
  -d "{\"request\": \"Create a project proposal for implementing an AI chatbot in a hospital.\"}"
```

**PowerShell Command:**
```powershell
Invoke-RestMethod -Uri http://127.0.0.1:8000/agent -Method Post -Body '{"request": "Create a project proposal for implementing an AI chatbot in a hospital."}' -ContentType "application/json" | ConvertTo-Json -Depth 5
```

**Success Response (200 OK):**
```json
{
  "status": "success",
  "tasks": [
    "Generate outline with key sections -> [completed]",
    "Write Executive Summary and Project Scope section -> [completed]",
    "Write Technology Stack and Integration section -> [completed]",
    "Write Implementation Timeline and Budget section -> [completed]",
    "Aggregate draft sections, format, and prepare draft -> [completed]"
  ],
  "assumptions": [
    "Assumed a target launch timeline of 6 months.",
    "Assumed standard hospital compliance (HIPAA) rules apply.",
    "Assumed integration with existing EHR (Electronic Health Record) systems."
  ],
  "document_type": "Project Proposal",
  "generated_file": "generated/project_proposal.docx",
  "preview": "# AI Chatbot Hospital Implementation Proposal\n\n## Executive Summary\nImplementing conversational AI chatbots in healthcare...",
  "execution_summary": "Successfully generated 'Project Proposal' in 14.32 seconds. Processed 5 pipeline tasks. Self-checking audit executed 1 verification step(s)."
}
```

---

## Technical Interview Preparation Notes

### 1. Architecture Explanation
The application is structured to decouple presentation (`app.py`), orchestration (`agent.py`), planning (`planner.py`), stateful run routing (`executor.py`), LLM query interfaces (`llm.py`), and content builders. Each layer communicates via strongly typed Pydantic models (`models.py`). The LLM interaction uses a single wrapper method `generate(prompt, system_prompt, response_format)` to simplify maintenance.

### 2. End-to-End Execution Workflow
1. Client POSTs a query -> `app.py` validates text length.
2. `AutonomousAgent` activates and triggers a high-resolution execution timer.
3. The query is classified by `PlannerAgent` returning document type, assumptions, and tool tasks.
4. The plan initializes the `ExecutorState` object.
5. The `Executor` runs the tasks, looking up actions (`generate_outline`, `generate_section`, `refine_content`) in the `Tool Registry`.
6. The `DocumentGenerator` crafts outline and sections, reading history to prevent repetitions.
7. The `Refiner` merges them into a single markdown draft.
8. The `ReflectionAgent` audits the draft for formatting/tone, requesting rewrites if issues occur.
9. `DocxGenerator` parses headings, bullet lists, bold text, and markdown tables to generate a `.docx` file.
10. The client receives a detailed response showing executed checklist steps and inferred metadata.

### 3. Debugging Story: Markdown-Wrapped JSON Outputs & Multi-Provider LLM Resilience
* **Symptom 1**: During integration testing, the Planner or Reflection agents occasionally crashed with `json.JSONDecodeError` because the LLM returned JSON inside markdown code blocks (e.g. ` ```json { ... } ``` `) instead of a raw JSON string.
* **Solution**: Developed a clean sanitization helper `_clean_json_markdown()` inside `llm.py` to strip out leading/trailing markdown blocks and whitespaces before parsing. Additionally, configured the Google GenAI client to request strict JSON mime-types (`response_mime_type="application/json"`).
* **Symptom 2**: Free-tier API quota exhaustion on both Gemini and Groq during heavy testing.
* **Solution**: Implemented a multi-provider LLM client in `llm.py` — Groq (`llama-3.3-70b-versatile`) is the primary provider with automatic fallback to `llama-3.1-8b-instant` (separate quota), then Gemini as final fallback. Each provider's quota errors are detected and handled gracefully without crashing the pipeline.
### 4. Engineering Trade-off: Autonomous Planning vs. Deterministic Workflows
* **Autonomous Planning**:
  * *Pros*: Handles open-ended and complex goals; dynamically adapts plan lengths and content headings; classifications adjust according to user intents.
  * *Cons*: Higher latency; risk of classification drift; validation is harder due to non-deterministic task outputs.
* **Deterministic Workflows**:
  * *Pros*: High reliability; fixed pricing/tokens; simpler validation; execution is highly reproducible.
  * *Cons*: Rigid structure; unable to adapt if the user submits unique requests or asks for unrelated layouts.
* *Our Hybrid Approach*: We use **Autonomous Planning** to structure the task list, but enforce a **Deterministic Executor Engine** with strict schema boundaries (`models.py`) and a strict `Tool Registry` whitelist. This allows flexibility in content generation while maintaining predictability in process execution.

### 5. Future System Scalability Improvements
* **Conversation Memory**: Track user revisions (e.g., "Add a compliance section") over multiple API calls.
* **True Tool Calling**: Integrate actual tools like live Web Searches or database queries using Gemini's native function calling interface.
* **RAG (Retrieval-Augmented Generation)**: Allow uploading corporate templates or business briefs to ground generated data against reality.
* **Vector Database**: Index compiled documents to search or compare past drafts.
* **LangGraph Migration**: Handle cyclical workflows and multi-agent coordination frameworks.
* **Asynchronous Execution (Celery/RabbitMQ)**: Offload document generation to background workers to prevent HTTP timeout issues for extremely long documents.
