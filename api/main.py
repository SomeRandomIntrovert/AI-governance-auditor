"""
FastAPI service wrapping the governance rubric.

This exists as a standalone HTTP service (rather than a plain script) so
that n8n orchestrates the audit the same way it would call any real
production API: an HTTP Request node hits POST /score, gets a structured
JSON result back, and appends it to the pipeline's output sink.

Run locally:
    uvicorn api.main:app --reload --port 8000

Endpoints:
    POST /score        - score a single workflow JSON, return full report
    GET  /health        - basic liveness check
"""

from __future__ import annotations
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Any
from .rubric import score_workflow

app = FastAPI(
    title="n8n Governance Auditor",
    description="Scores exported n8n workflow JSON against a governance rubric "
                 "(credential exposure, error handling, autonomy tier, audit trail).",
    version="0.1.0",
)


class ScoreRequest(BaseModel):
    filename: str = ""
    workflow: dict[str, Any]


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/score")
def score(req: ScoreRequest) -> dict[str, Any]:
    if not req.workflow or "nodes" not in req.workflow:
        raise HTTPException(status_code=400, detail="Payload missing a valid n8n 'workflow' object with a 'nodes' array.")
    try:
        return score_workflow(req.workflow, filename=req.filename)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Scoring failed: {e}")
