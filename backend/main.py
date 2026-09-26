"""
Argus FastAPI backend.

Responsibilities:
- Accept GitHub repository URLs (public or private with token).
- Clone the repository.
- Run the optimized security-analysis orchestrator.
- Generate a PDF report.
- Return findings, routing information, and performance metrics.
"""

import json
import queue
import shutil
import tempfile
import threading
import time
import uuid
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.encoders import jsonable_encoder
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field

from agents import ALL_AGENTS
from audio_forensics.api import router as audio_router
from github import clone_repository, normalize_github_url, summarize_repository
from orchestrator import SecurityOrchestrator
from report import generate_pdf_report


app = FastAPI(
    title="Argus Security Scanner",
    version="1.1.0"
)


app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "https://argus-six-smoky.vercel.app/",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)

app.include_router(audio_router)

security_orchestrator = SecurityOrchestrator()

REPORT_DIRECTORY = Path("reports")
REPORT_DIRECTORY.mkdir(exist_ok=True)


class AnalyzeRequest(BaseModel):
    repository_url: str = Field(
        ...,
        min_length=1,
        description="GitHub repository URL"
    )

    scan_profile: str = Field(
        default="standard",
        description="quick, standard, or deep"
    )

    github_token: str | None = Field(
        default=None,
        description=(
            "Optional GitHub personal access token with `repo` scope "
            "for private repositories"
        )
    )


def serialize_findings(findings):
    """
    Convert Pydantic SecurityFinding objects into JSON-compatible data.
    """

    serialized_findings = []

    for finding in findings:
        if hasattr(finding, "model_dump"):
            serialized_findings.append(
                finding.model_dump()
            )
        else:
            serialized_findings.append(finding)

    return serialized_findings


def serialize_agent_results(agent_results):
    """
    Normalize agent result payloads for the API response.
    """

    serialized = []

    for result in agent_results:
        findings = result.get("findings", [])
        serialized_findings = serialize_findings(findings)

        serialized.append({
            "agent_name": result.get("agent_name"),
            "status": result.get("status"),
            "reason": result.get("reason"),
            "elapsed_seconds": result.get("elapsed_seconds", 0),
            "files_analyzed": result.get("files_analyzed", []),
            "findings_count": len(serialized_findings),
            "findings": serialized_findings
        })

    return serialized


def calculate_severity_summary(findings):
    """
    Count findings by severity.
    """

    summary = {
        "Critical": 0,
        "High": 0,
        "Medium": 0,
        "Low": 0,
        "Informational": 0
    }

    for finding in findings:
        severity = finding.get("severity")

        if severity in summary:
            summary[severity] += 1

    return summary


BASELINE_SECONDS = {
    "quick": 20,
    "standard": 75,
    "deep": 90,
}


def estimate_remaining_seconds(elapsed, percent, scan_profile):
    """
    Blend a profile baseline with the time already spent.

    Early stages stay close to the baseline. Later stages trust
    the observed pace, so the estimate tightens as the scan moves.
    """

    baseline = BASELINE_SECONDS.get(scan_profile, 75)

    if percent >= 99:
        return 0

    if percent <= 3:
        return max(1, round(baseline - elapsed))

    observed_total = elapsed / (percent / 100.0)
    trust = min(1.0, max(0.0, (percent - 8) / 40.0))
    estimated_total = (
        baseline * (1 - trust)
        + observed_total * trust
    )

    return max(1, round(estimated_total - elapsed))


def progress_event(percent, message, elapsed, scan_profile):
    return {
        "type": "progress",
        "percent": round(percent, 1),
        "message": message,
        "elapsed_seconds": round(elapsed, 1),
        "estimated_remaining_seconds": estimate_remaining_seconds(
            elapsed,
            percent,
            scan_profile
        ),
    }


def execute_scan(request, scan_id, temporary_directory, on_progress):
    """
    Clone a repository, analyze it, and write the PDF report.
    """

    repository_url = normalize_github_url(
        request.repository_url
    )

    print(
        f"\nStarting scan for: "
        f"{repository_url}"
    )

    print(
        f"Scan profile: {request.scan_profile}"
    )

    if request.scan_profile == "quick":
        on_progress(2, 16, "Cloning the repository")
    else:
        on_progress(2, 12, "Cloning the repository")

    repository_path = clone_repository(
        repository_url=repository_url,
        destination_directory=temporary_directory,
        github_token=request.github_token
    )

    analysis_result = (
        security_orchestrator.analyze_repository(
            repository_path=repository_path,
            scan_profile=request.scan_profile,
            on_progress=on_progress
        )
    )

    findings = analysis_result.get(
        "findings",
        []
    )

    serialized_findings = serialize_findings(
        findings
    )

    severity_summary = calculate_severity_summary(
        serialized_findings
    )

    if request.scan_profile == "quick":
        on_progress(90, 99, "Writing the PDF report")
    else:
        on_progress(94, 99, "Writing the PDF report")

    report_path = REPORT_DIRECTORY / (
        f"{scan_id}.pdf"
    )

    generate_pdf_report(
        findings=findings,
        output_path=str(report_path),
        repository_url=repository_url
    )

    routing = analysis_result.get(
        "routing",
        {}
    )

    agent_results = serialize_agent_results(
        analysis_result.get(
            "agent_results",
            []
        )
    )

    repository_analysis = analysis_result.get(
        "repository_analysis",
        {}
    )

    repository_overview = summarize_repository(
        repository_path=repository_path,
        repository_url=repository_url,
        languages=repository_analysis.get("languages", []),
        github_token=request.github_token
    )

    return {
        "scan_id": scan_id,
        "repository_url": repository_url,
        "scan_profile": request.scan_profile,
        "repository_overview": repository_overview,

        "files_analyzed": analysis_result.get(
            "files_collected",
            0
        ),

        "findings": serialized_findings,

        "summary": {
            "total_findings": len(serialized_findings),
            "severity": severity_summary,
            "rule_findings": analysis_result.get(
                "rule_findings",
                0
            ),
            "llm_findings": analysis_result.get(
                "llm_findings",
                0
            )
        },

        "routing": routing,

        "preprocessing": {
            "languages": repository_analysis.get(
                "languages",
                []
            ),
            "signals": list(
                repository_analysis.get(
                    "signals",
                    {}
                ).keys()
            ),
            "total_signal_count": repository_analysis.get(
                "total_signal_count",
                0
            )
        },

        "agent_results": agent_results,

        "timing": analysis_result.get(
            "timing",
            {}
        ),

        "report_url": (
            f"/api/report/{scan_id}"
        )
    }


def stream_scan(request, scan_id, temporary_directory):
    """
    Run a scan on a background thread and yield live progress events.
    """

    events = queue.Queue()
    started_at = time.perf_counter()

    def on_progress(percent, ceiling, message):
        events.put({
            "type": "progress",
            "percent": percent,
            "ceiling": ceiling,
            "message": message,
        })

    def worker():
        try:
            result = execute_scan(
                request,
                scan_id,
                temporary_directory,
                on_progress
            )
            events.put({
                "type": "complete",
                "result": jsonable_encoder(result),
            })
        except Exception as error:
            print(
                f"Scan failed: {error}"
            )
            events.put({
                "type": "error",
                "detail": str(error),
            })
        finally:
            shutil.rmtree(
                temporary_directory,
                ignore_errors=True
            )

    threading.Thread(
        target=worker,
        daemon=True
    ).start()

    displayed_percent = 1.0
    ceiling = 4.0
    message = "Starting the scan"

    yield encode_event(
        progress_event(
            displayed_percent,
            message,
            0,
            request.scan_profile
        )
    )

    while True:
        try:
            item = events.get(timeout=0.4)
        except queue.Empty:
            gap = ceiling - displayed_percent

            if gap > 0.3:
                displayed_percent = min(
                    ceiling,
                    displayed_percent + max(0.3, gap * 0.07)
                )

            elapsed = time.perf_counter() - started_at
            yield encode_event(
                progress_event(
                    displayed_percent,
                    message,
                    elapsed,
                    request.scan_profile
                )
            )
            continue

        elapsed = time.perf_counter() - started_at

        if item["type"] == "progress":
            displayed_percent = max(
                displayed_percent,
                float(item["percent"])
            )
            ceiling = max(
                displayed_percent,
                float(item["ceiling"])
            )
            message = item["message"]
            yield encode_event(
                progress_event(
                    displayed_percent,
                    message,
                    elapsed,
                    request.scan_profile
                )
            )
            continue

        if item["type"] == "error":
            yield encode_event({
                "type": "error",
                "detail": item["detail"],
            })
            return

        yield encode_event(
            progress_event(
                100,
                "Scan complete",
                elapsed,
                request.scan_profile
            )
        )
        yield encode_event({
            "type": "complete",
            "result": item["result"],
        })
        return


def encode_event(payload):
    return f"data: {json.dumps(payload)}\n\n"


def get_agent_catalog():
    """
    Return metadata for all registered security agents.
    """

    catalog = []

    for agent_class in ALL_AGENTS:
        agent = agent_class()

        catalog.append({
            "name": agent.name,
            "vulnerability_type": agent.vulnerability_type,
            "trigger_signals": agent.trigger_signals,
            "category": _agent_category(agent.name)
        })

    return catalog


def _agent_category(agent_name):
    """
    Map agent names to display categories for the frontend.
    """

    categories = {
        "SQL Injection Agent": "web",
        "Cross-Site Scripting Agent": "web",
        "Hardcoded Secrets Agent": "secrets",
        "Binary Exploitation Agent": "pwn",
        "Reverse Engineering Agent": "rev",
        "Low-Level & Memory Security Agent": "pwn",
        "HTTP Header Injection Agent": "web"
    }

    return categories.get(agent_name, "general")


@app.get("/")
def root():
    return {
        "name": "Argus Security Scanner",
        "status": "running",
        "version": "1.1.0"
    }


@app.get("/api/health")
def health_check():
    return {
        "status": "healthy"
    }


@app.get("/api/agents")
def list_agents():
    """
    Return all available security agents and their routing signals.
    """

    return {
        "agents": get_agent_catalog(),
        "total": len(ALL_AGENTS)
    }


@app.get("/api/capabilities")
def scan_capabilities():
    """
    Describe supported scan profiles and repository access options.
    """

    return {
        "scan_profiles": [
            {
                "id": "quick",
                "name": "Quick Scan",
                "description": (
                    "Deterministic rules only — no AI agents"
                )
            },
            {
                "id": "standard",
                "name": "Standard Scan",
                "description": (
                    "Rules plus routed Gemini agents for relevant signals"
                )
            },
            {
                "id": "deep",
                "name": "Deep Scan",
                "description": (
                    "Full rules and all routed agents with extended analysis"
                )
            }
        ],
        "repository_access": {
            "public": True,
            "private": True,
            "private_requirements": (
                "GitHub personal access token with `repo` scope, "
                "supplied via github_token in the request body or "
                "GITHUB_TOKEN environment variable"
            )
        },
        "llm_provider": "Google Gemini",
        "agent_count": len(ALL_AGENTS)
    }


@app.post("/api/analyze")
def analyze_repository(request: AnalyzeRequest):
    """
    Clone and analyze a GitHub repository.

    The response is a stream of progress events, followed by the
    finished scan or an error event.
    """

    allowed_profiles = {
        "quick",
        "standard",
        "deep"
    }

    if request.scan_profile not in allowed_profiles:
        raise HTTPException(
            status_code=400,
            detail=(
                "Invalid scan profile. "
                "Choose quick, standard, or deep."
            )
        )

    temporary_directory = tempfile.mkdtemp(
        prefix="argus_scan_"
    )

    scan_id = str(uuid.uuid4())

    return StreamingResponse(
        stream_scan(
            request,
            scan_id,
            temporary_directory
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
    )


@app.get("/api/report/{scan_id}")
def download_report(scan_id: str):
    """
    Return a generated PDF report.
    """

    report_path = REPORT_DIRECTORY / (
        f"{scan_id}.pdf"
    )

    if not report_path.exists():
        raise HTTPException(
            status_code=404,
            detail="Report not found"
        )

    return FileResponse(
        path=str(report_path),
        media_type="application/pdf",
        filename=f"argus-report-{scan_id}.pdf"
    )
