"""
main.py — FastAPI application for Page Pulse.

Serves the audit API endpoint and dynamic Jinja2 frontend template.
"""

from __future__ import annotations

from typing import Optional
from fastapi import FastAPI, Request, Form, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from backend.auditor import audit_url, AuditReport, AuditError

# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Page Pulse",
    description="A lightweight web-page auditing tool.",
    version="1.0.0",
)

# CORS — allow any origin so the frontend can call from anywhere
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

templates = Jinja2Templates(directory="templates")


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------

class AuditRequest(BaseModel):
    url: str


# ---------------------------------------------------------------------------
# Dynamic HTML Page Route
# ---------------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
async def home(request: Request, url: Optional[str] = Query(None)):
    """
    Renders the dynamic home page.
    If a `url` query param is provided, audits it on the server side and
    pre-populates the template with initial audit results.
    """
    initial_report = None
    initial_error = None

    if url:
        result = await audit_url(url)
        if isinstance(result, AuditError):
            initial_error = result.to_dict()
        else:
            initial_report = result.to_dict()

    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "initial_url": url or "",
            "initial_report": initial_report,
            "initial_error": initial_error,
        },
    )


# ---------------------------------------------------------------------------
# API endpoint
# ---------------------------------------------------------------------------

@app.post("/api/audit")
async def audit_endpoint(payload: AuditRequest):
    """
    Accept a URL and return an audit report as JSON.

    Returns
    -------
    - 200 with the report on success.
    - 400 for invalid URLs.
    - 415 for non-HTML responses.
    - 504 for timeouts or connection errors.
    """
    result = await audit_url(payload.url)

    if isinstance(result, AuditError):
        status_map = {
            "invalid_url": 400,
            "timeout": 504,
            "connection_error": 502,
            "request_error": 502,
            "not_html": 415,
        }
        http_status = status_map.get(result.error, 500)
        return JSONResponse(content=result.to_dict(), status_code=http_status)

    return JSONResponse(content=result.to_dict(), status_code=200)


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

@app.get("/api/health")
async def health():
    return {"status": "ok"}

