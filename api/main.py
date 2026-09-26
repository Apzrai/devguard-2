"""
api/main.py — FastAPI REST layer over the DEVGUARD Python engine.

This module is a thin HTTP interface.  All business logic lives in the
devguard/ package.  This file only:
  - Declares routes and Pydantic request/response models.
  - Calls the existing DEVGUARD functions.
  - Returns their serialised output as JSON.

Architecture:
  React frontend
       ↓
  FastAPI REST API   (this file)
       ↓
  DEVGUARD engine    (devguard/*.py — unchanged)
       ↓
  sample_app/        (the project being analysed — unchanged)

Start the server:
  uvicorn api.main:app --reload --port 8000

Swagger UI:  http://localhost:8000/docs
OpenAPI:     http://localhost:8000/openapi.json
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# DEVGUARD engine imports (nothing else is imported — no logic lives here)
# ---------------------------------------------------------------------------
from devguard.understand import understand
from devguard.behavior_map import build_behavior_map
from devguard.evidence import collect_evidence
from devguard.contract import (
    build_contract,
    make_enterprise_discount_request,
    MaintenanceRequest,
)
from devguard.impact import analyze_impact
from devguard.bob_task import build_bob_task
from devguard.bob_executor import get_executor, BobResponse
from devguard.drift_detector import detect_drift
from devguard.verifier import verify
from devguard.proof import build_proof

# ---------------------------------------------------------------------------
# App initialisation
# ---------------------------------------------------------------------------

app = FastAPI(
    title="DEVGUARD API",
    description=(
        "REST interface for the DEVGUARD behavioral-contract engine. "
        "Exposes the six-phase analysis/execution pipeline to React frontends."
    ),
    version="1.0.0",
    docs_url="/docs",
    openapi_url="/openapi.json",
)

# ---------------------------------------------------------------------------
# CORS — allow React dev servers on common local ports
# Edit ALLOWED_ORIGINS (or set the DEVGUARD_CORS_ORIGINS env var as a
# comma-separated list) to add your deployed frontend URL later.
# ---------------------------------------------------------------------------

_DEFAULT_ORIGINS = [
    "http://localhost:3000",
    "http://localhost:5173",
]

ALLOWED_ORIGINS: list[str] = [
    o.strip()
    for o in os.environ.get("DEVGUARD_CORS_ORIGINS", ",".join(_DEFAULT_ORIGINS)).split(",")
    if o.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Workspace root — the directory that contains sample_app/
# The DEVGUARD_PROJECT_ROOT env var overrides the default (repo root).
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).resolve().parent.parent   # …/devguard/
_DEFAULT_SAMPLE_APP = _REPO_ROOT / "sample_app"

def _sample_app_root() -> Path:
    """Return the path to sample_app/, honoring DEVGUARD_PROJECT_ROOT if set."""
    override = os.environ.get("DEVGUARD_PROJECT_ROOT")
    if override:
        p = Path(override)
        if not p.is_dir():
            raise ValueError(f"DEVGUARD_PROJECT_ROOT is not a directory: {p}")
        return p
    return _DEFAULT_SAMPLE_APP


# ---------------------------------------------------------------------------
# Pydantic request models
# ---------------------------------------------------------------------------

class AnalyzeRequest(BaseModel):
    """Body for POST /api/repository/analyze."""
    project_root: str | None = Field(
        default=None,
        description=(
            "Absolute or relative path to the project root to analyse. "
            "Defaults to the bundled sample_app/."
        ),
    )


class MaintenanceRequestBody(BaseModel):
    """Body for POST /api/maintenance.
    All fields are optional; omitting them uses the canonical demo values.
    """
    request_id: str | None = None
    description: str | None = None
    target_behavior_id: str = Field(default="B003")
    target_symbol: str = Field(default="ENTERPRISE_DISCOUNT")
    target_file: str = Field(default="customers.py")
    current_value: str = Field(default="0.10")
    requested_value: str = Field(default="0.15")
    requestor: str = Field(default="developer")
    notes: str = Field(default="")


class ContractRequest(BaseModel):
    """Body for POST /api/contract."""
    project_root: str | None = None
    maintenance: MaintenanceRequestBody = Field(default_factory=MaintenanceRequestBody)


class ImpactRequest(BaseModel):
    """Body for POST /api/impact."""
    project_root: str | None = None
    maintenance: MaintenanceRequestBody = Field(default_factory=MaintenanceRequestBody)


class BobTaskRequest(BaseModel):
    """Body for POST /api/bob-task."""
    project_root: str | None = None
    maintenance: MaintenanceRequestBody = Field(default_factory=MaintenanceRequestBody)


class DriftRequest(BaseModel):
    """Body for POST /api/drift.
    Runs the full pipeline up to Bob execution and then detects intent drift.
    """
    project_root: str | None = None
    maintenance: MaintenanceRequestBody = Field(default_factory=MaintenanceRequestBody)
    bob_backend: str = Field(
        default="mock",
        description="Bob executor backend: 'mock', 'watsonx_llm', or 'watsonx_agent'.",
    )
    bob_scenario: str = Field(
        default="failure",
        description="For mock backend only: 'failure' (default) or 'success'.",
    )


class VerifyRequest(BaseModel):
    """Body for POST /api/verify.
    Runs the full pipeline through drift detection and then verifies.
    """
    project_root: str | None = None
    maintenance: MaintenanceRequestBody = Field(default_factory=MaintenanceRequestBody)
    bob_backend: str = Field(default="mock")
    bob_scenario: str = Field(default="failure")


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

import uuid as _uuid


def _resolve_root(override: str | None) -> Path:
    """Return the project root path from the request or from the default."""
    if override:
        p = Path(override)
        if not p.is_dir():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"project_root is not a directory: {override}",
            )
        return p
    return _sample_app_root()


def _build_maintenance_request(body: MaintenanceRequestBody) -> MaintenanceRequest:
    """Construct a MaintenanceRequest from the API body, using canonical defaults."""
    import uuid
    return MaintenanceRequest(
        request_id=body.request_id or str(uuid.uuid4()),
        description=body.description or "Update the Enterprise discount from 10% to 15%.",
        target_behavior_id=body.target_behavior_id,
        target_symbol=body.target_symbol,
        target_file=body.target_file,
        current_value=body.current_value,
        requested_value=body.requested_value,
        requestor=body.requestor,
        notes=body.notes,
    )


def _run_pipeline_to_contract(
    root: Path,
    maint: MaintenanceRequestBody,
) -> tuple[Any, Any, Any, Any, MaintenanceRequest]:
    """Run phases 1–3: understand → behavior_map → evidence → contract.
    Returns (u, bmap, ev, contract, request).
    """
    u = understand(root)
    bmap = build_behavior_map(u)
    ev = collect_evidence(u)
    request = _build_maintenance_request(maint)
    contract = build_contract(bmap, request)
    return u, bmap, ev, contract, request


def _run_pipeline_to_bob_response(
    root: Path,
    maint: MaintenanceRequestBody,
    bob_backend: str,
    bob_scenario: str,
) -> tuple[Any, Any, Any, Any, Any, Any, MaintenanceRequest, Any]:
    """Run phases 1–5: understand → … → bob execution.
    Returns (u, bmap, ev, contract, impact, task, request, response).
    """
    u, bmap, ev, contract, request = _run_pipeline_to_contract(root, maint)
    impact = analyze_impact(u, bmap, contract)
    task = build_bob_task(u, bmap, ev, contract, impact, request)
    executor = get_executor(backend=bob_backend, scenario=bob_scenario)
    response = executor.execute(task)
    return u, bmap, ev, contract, impact, task, request, response


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/api/health", tags=["health"])
def health_check() -> dict:
    """Return a simple health check confirming the DEVGUARD API is running."""
    return {
        "status": "ok",
        "service": "DEVGUARD API",
        "version": "1.0.0",
    }


@app.post("/api/repository/analyze", tags=["pipeline"])
def analyze_repository(body: AnalyzeRequest = None) -> dict:
    """Phase 1 — Project Understanding.

    Analyses the target project using static analysis (Python AST).
    Returns the full ProjectUnderstanding record.
    """
    if body is None:
        body = AnalyzeRequest()
    root = _resolve_root(body.project_root)
    try:
        u = understand(root)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    return u.to_dict()


@app.post("/api/maintenance", tags=["pipeline"])
def create_maintenance(body: MaintenanceRequestBody = None) -> dict:
    """Phase 2a — Maintenance Request.

    Constructs a structured MaintenanceRequest from the supplied parameters.
    All fields are optional; defaults target the canonical ENTERPRISE_DISCOUNT
    demo scenario (B003: 0.10 → 0.15).
    """
    if body is None:
        body = MaintenanceRequestBody()
    request = _build_maintenance_request(body)
    return request.to_dict()


@app.post("/api/contract", tags=["pipeline"])
def create_contract(body: ContractRequest = None) -> dict:
    """Phases 1–3 — Behavioral Contract.

    Runs understand → behavior_map → contract.
    Returns the full BehavioralContract record including protected clauses
    and success criteria.
    """
    if body is None:
        body = ContractRequest()
    root = _resolve_root(body.project_root)
    try:
        _, _, _, contract, _ = _run_pipeline_to_contract(root, body.maintenance)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    return contract.to_dict()


@app.post("/api/impact", tags=["pipeline"])
def analyze_impact_endpoint(body: ImpactRequest = None) -> dict:
    """Phases 1–4 — Impact Analysis.

    Runs understand → behavior_map → contract → impact analysis.
    Returns directly_affected files, indirectly_affected files,
    at-risk tests, and a risk summary.
    """
    if body is None:
        body = ImpactRequest()
    root = _resolve_root(body.project_root)
    try:
        u, bmap, _, contract, _ = _run_pipeline_to_contract(root, body.maintenance)
        impact = analyze_impact(u, bmap, contract)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    return impact.to_dict()


@app.post("/api/bob-task", tags=["pipeline"])
def build_bob_task_endpoint(body: BobTaskRequest = None) -> dict:
    """Phases 1–5a — BobTask Assembly.

    Runs the full DEVGUARD pipeline through impact analysis and assembles
    a BobTask — the structured handoff package ready for IBM Bob.
    Returns the complete BobTask including the ready-to-use Bob prompt.
    """
    if body is None:
        body = BobTaskRequest()
    root = _resolve_root(body.project_root)
    try:
        u, bmap, ev, contract, request = _run_pipeline_to_contract(root, body.maintenance)
        impact = analyze_impact(u, bmap, contract)
        task = build_bob_task(u, bmap, ev, contract, impact, request)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    return task.to_dict()


@app.post("/api/drift", tags=["pipeline"])
def detect_drift_endpoint(body: DriftRequest = None) -> dict:
    """Phases 1–5b — Intent Drift Detection.

    Runs the full pipeline including Bob execution (using the specified
    backend/scenario), then analyses the proposed diff for intent drift.

    Returns the DriftResult: intended vs. unintended changes,
    protected-behavior violations, and a CLEAR / DRIFT_DETECTED status.

    bob_backend options: 'mock' (default), 'watsonx_llm', 'watsonx_agent'
    bob_scenario options (mock only): 'failure' (default), 'success'
    """
    if body is None:
        body = DriftRequest()
    root = _resolve_root(body.project_root)
    try:
        _, _, _, contract, _, _, _, response = _run_pipeline_to_bob_response(
            root, body.maintenance, body.bob_backend, body.bob_scenario
        )
        drift = detect_drift(contract, response)
    except (ValueError, NotImplementedError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    return drift.to_dict()


@app.post("/api/verify", tags=["pipeline"])
def verify_endpoint(body: VerifyRequest = None) -> dict:
    """Phases 1–6a — Behavioral Verification.

    Runs the full pipeline through Bob execution, drift detection, and
    finally behavioral verification (creates a working copy, applies the
    proposed diff, runs the test suite, reports pass/fail).

    WARNING: This endpoint creates a temporary working copy of sample_app
    and runs pytest against it.  It is slower than the other endpoints
    (typically 5–30 seconds).

    Returns a VerificationResult with test counts, failed test IDs,
    and a contract_satisfied verdict.
    """
    if body is None:
        body = VerifyRequest()
    root = _resolve_root(body.project_root)
    try:
        u, bmap, ev, contract, impact, task, request, response = (
            _run_pipeline_to_bob_response(
                root, body.maintenance, body.bob_backend, body.bob_scenario
            )
        )
        drift = detect_drift(contract, response)
        result = verify(contract, response, drift, root)
    except (ValueError, NotImplementedError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    return result.to_dict()


@app.get("/api/proof", tags=["pipeline"])
def get_proof_endpoint(
    bob_backend: str = "mock",
    bob_scenario: str = "failure",
    project_root: str | None = None,
) -> dict:
    """Phase 6 — Proof of Done.

    Runs the complete six-phase DEVGUARD pipeline and returns a
    ProofOfDone record summarising the final status (VERIFIED or
    BLOCKED / FAILED), test results, intent drift findings, and whether
    the behavioral contract was satisfied.

    Query parameters:
      bob_backend  — 'mock' (default), 'watsonx_llm', 'watsonx_agent'
      bob_scenario — 'failure' (default) or 'success'  [mock backend only]
      project_root — override the default sample_app/ path

    WARNING: Triggers a full verification run including pytest execution.
    """
    root = _resolve_root(project_root)
    maint = MaintenanceRequestBody()   # canonical defaults
    try:
        u, bmap, ev, contract, impact, task, request, response = (
            _run_pipeline_to_bob_response(root, maint, bob_backend, bob_scenario)
        )
        drift = detect_drift(contract, response)
        verification = verify(contract, response, drift, root)
        proof = build_proof(request, contract, response, drift, verification)
    except (ValueError, NotImplementedError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    return proof.to_dict()
