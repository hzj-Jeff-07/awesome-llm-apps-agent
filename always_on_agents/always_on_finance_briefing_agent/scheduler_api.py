"""Scheduler-facing API for FinanceScout.

Run locally with:
    uvicorn scheduler_api:app --host 0.0.0.0 --port 8000
"""

from __future__ import annotations

import base64
import json
from json import JSONDecodeError
from typing import Any, Optional

from fastapi import FastAPI, Request

try:
    from .article import render_wechat_article
    from .delivery import send_brief
    from .scout import run_finance_scout
except ImportError:
    from article import render_wechat_article
    from delivery import send_brief
    from scout import run_finance_scout

app = FastAPI(
    title="FinanceScout Scheduler API",
    description="HTTP and Pub/Sub hooks for scheduled SEC EDGAR briefing runs.",
)


def _as_bool(value: Any, *, default: bool | None = None) -> bool | None:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.lower()
        if lowered in {"1", "true", "yes"}:
            return True
        if lowered in {"0", "false", "no"}:
            return False
    return default


def _as_top_n(value: Any) -> int:
    try:
        top_n = int(value)
    except (TypeError, ValueError):
        return 5
    return max(1, min(top_n, 10))


def run_scheduled_scout(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    """Run FinanceScout from a scheduler payload.

    Payload fields:
        dry_run: defaults to true. Set false to call configured delivery.
        live: optional override for live EDGAR mode.
        top_n: number of filings, clamped to 1-10.
        include_article: defaults to true. Set false to skip the WeChat article.
    """

    payload = payload if isinstance(payload, dict) else {}
    dry_run = _as_bool(payload.get("dry_run"), default=True)
    live = _as_bool(payload.get("live"), default=None)
    include_article = _as_bool(payload.get("include_article"), default=True)
    top_n = _as_top_n(payload.get("top_n"))

    brief = run_finance_scout(live=live, top_n=top_n)
    if include_article:
        brief["article"] = render_wechat_article(brief)

    delivery = {
        "attempted": False,
        "sent": False,
        "status": "dry_run",
        "detail": "Set dry_run=false to use configured Gmail or webhook delivery.",
    }
    if dry_run is False:
        delivery = {"attempted": True, **send_brief(brief)}

    return {
        "dry_run": dry_run,
        "top_n": top_n,
        "delivery": delivery,
        "brief": brief,
    }


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/finance-brief/dry-run")
def dry_run_preview(top_n: int = 5, live: Optional[bool] = None) -> dict[str, Any]:
    return run_scheduled_scout({"dry_run": True, "top_n": top_n, "live": live})


@app.post("/finance-brief/trigger")
async def scheduler_trigger(request: Request) -> dict[str, Any]:
    try:
        payload = await request.json() if request.headers.get("content-length") else {}
    except JSONDecodeError:
        payload = {}
    return run_scheduled_scout(payload)


@app.post("/finance-brief/pubsub")
async def pubsub_trigger(request: Request) -> dict[str, Any]:
    """Cloud Scheduler -> Pub/Sub push compatible endpoint."""

    envelope = await request.json()
    message = envelope.get("message", {}) if isinstance(envelope, dict) else {}
    payload: dict[str, Any] = {}
    encoded_data = message.get("data")
    if encoded_data:
        try:
            decoded = base64.b64decode(encoded_data).decode("utf-8")
            payload = json.loads(decoded)
        except (ValueError, JSONDecodeError):
            payload = {}
    return run_scheduled_scout(payload)
