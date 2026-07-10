"""Optional delivery hooks for scheduled FinanceScout runs."""

from __future__ import annotations

import base64
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from email.message import EmailMessage
from typing import Any


GMAIL_REQUIRED_ENV = [
    "FINBRIEF_EMAIL_TO",
    "FINBRIEF_EMAIL_FROM",
    "FINBRIEF_GMAIL_CLIENT_ID",
    "FINBRIEF_GMAIL_CLIENT_SECRET",
    "FINBRIEF_GMAIL_REFRESH_TOKEN",
]


def send_brief(payload: dict[str, Any]) -> dict[str, Any]:
    """Send a rendered brief through Gmail or a webhook.

    Delivery is intentionally opt-in. If FINBRIEF_DELIVERY is unset, Gmail is
    preferred when fully configured, then webhook delivery, then a skipped status.
    """

    delivery_mode = os.environ.get("FINBRIEF_DELIVERY", "auto").lower()
    if delivery_mode == "gmail":
        return send_gmail(payload)
    if delivery_mode == "webhook":
        return send_webhook(payload)
    if _gmail_configured():
        return send_gmail(payload)
    if os.environ.get("FINBRIEF_WEBHOOK_URL"):
        return send_webhook(payload)
    return {
        "configured": False,
        "sent": False,
        "status": "skipped_no_delivery",
        "detail": (
            "Set Gmail environment variables or FINBRIEF_WEBHOOK_URL to deliver "
            "scheduled briefs."
        ),
    }


def _gmail_configured() -> bool:
    return all(os.environ.get(name) for name in GMAIL_REQUIRED_ENV)


def _missing_gmail_config() -> list[str]:
    return [name for name in GMAIL_REQUIRED_ENV if not os.environ.get(name)]


def _fetch_gmail_access_token() -> str:
    request = urllib.request.Request(
        "https://oauth2.googleapis.com/token",
        data=urllib.parse.urlencode(
            {
                "client_id": os.environ["FINBRIEF_GMAIL_CLIENT_ID"],
                "client_secret": os.environ["FINBRIEF_GMAIL_CLIENT_SECRET"],
                "refresh_token": os.environ["FINBRIEF_GMAIL_REFRESH_TOKEN"],
                "grant_type": "refresh_token",
            }
        ).encode("utf-8"),
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        token_payload = json.loads(response.read().decode("utf-8"))
    return str(token_payload["access_token"])


def send_gmail(payload: dict[str, Any]) -> dict[str, Any]:
    """Send the rendered brief through the Gmail API."""

    missing = _missing_gmail_config()
    if missing:
        return {
            "provider": "gmail",
            "configured": False,
            "sent": False,
            "status": "skipped_missing_gmail_config",
            "missing": missing,
        }

    try:
        access_token = _fetch_gmail_access_token()
        message = EmailMessage()
        message["To"] = os.environ["FINBRIEF_EMAIL_TO"]
        message["From"] = os.environ["FINBRIEF_EMAIL_FROM"]
        message["Subject"] = payload["subject"]
        message.set_content(payload["text"])
        message.add_alternative(payload["html"], subtype="html")

        encoded_message = base64.urlsafe_b64encode(message.as_bytes()).decode("ascii")
        request = urllib.request.Request(
            "https://gmail.googleapis.com/gmail/v1/users/me/messages/send",
            data=json.dumps({"raw": encoded_message}).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=20) as response:
            response_payload = json.loads(response.read().decode("utf-8"))
        return {
            "provider": "gmail",
            "configured": True,
            "sent": True,
            "status": "sent",
            "message_id": response_payload.get("id"),
            "thread_id": response_payload.get("threadId"),
        }
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        return {
            "provider": "gmail",
            "configured": True,
            "sent": False,
            "status": exc.code,
            "error": detail[:500],
        }
    except (KeyError, urllib.error.URLError, TimeoutError) as exc:
        return {
            "provider": "gmail",
            "configured": True,
            "sent": False,
            "status": "connection_error",
            "error": str(exc),
        }


def send_webhook(payload: dict[str, Any]) -> dict[str, Any]:
    """Send a rendered brief to a configured webhook.

    The app stays safe by default: no webhook is called unless
    FINBRIEF_WEBHOOK_URL is present. Point the webhook at a WeCom (企业微信),
    Feishu, Slack, or Telegram bot endpoint to reach subscribers directly.
    """

    webhook_url = os.environ.get("FINBRIEF_WEBHOOK_URL")
    if not webhook_url:
        return {
            "provider": "webhook",
            "configured": False,
            "sent": False,
            "status": "skipped_no_webhook",
            "detail": "Set FINBRIEF_WEBHOOK_URL to deliver scheduled briefs.",
        }

    body = json.dumps(
        {
            "subject": payload["subject"],
            "text": payload["text"],
            "html": payload["html"],
            "filings": payload["filings"],
            "next_actions": payload["next_actions"],
            "article": payload.get("article"),
        }
    ).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    token = os.environ.get("FINBRIEF_WEBHOOK_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"

    request = urllib.request.Request(
        webhook_url,
        data=body,
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            response_text = response.read().decode("utf-8", errors="replace")
            return {
                "provider": "webhook",
                "configured": True,
                "sent": 200 <= response.status < 300,
                "status": response.status,
                "response": response_text[:500],
            }
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        return {
            "provider": "webhook",
            "configured": True,
            "sent": False,
            "status": exc.code,
            "error": detail[:500],
        }
    except urllib.error.URLError as exc:
        return {
            "provider": "webhook",
            "configured": True,
            "sent": False,
            "status": "connection_error",
            "error": str(exc),
        }
