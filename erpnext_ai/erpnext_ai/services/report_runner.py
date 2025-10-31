from __future__ import annotations

import json
from typing import Any, Dict, Optional

import frappe
from frappe.utils import now_datetime

from erpnext_ai.erpnext_ai.doctype.ai_settings.ai_settings import (
    AISettings,
    DEFAULT_PROMPT,
    DEFAULT_TIMEOUT,
)
from .admin_summary import collect_admin_context
from .openai_client import generate_completion


SYSTEM_PROMPT = (
    "You are an ERPNext AI copilot for company administrators. "
    "Summarise the provided context and surface risks, opportunities, and action points."
)


def _ensure_permission() -> None:
    if not frappe.has_permission("AI Report", "write"):
        frappe.throw("You are not permitted to run AI reports.", frappe.PermissionError)  # noqa: TRY003


def _format_prompt(template: str, context: Dict[str, Any]) -> str:
    context_json = json.dumps(context, indent=2, default=str)
    return template.replace("{context}", context_json)


def _coerce_days(days: Any) -> int:
    try:
        return int(days)
    except (TypeError, ValueError):
        return 30


def generate_admin_report(
    *,
    title: Optional[str] = None,
    custom_prompt: Optional[str] = None,
    days: int = 30,
) -> Dict[str, Any]:
    _ensure_permission()

    settings = AISettings.get_settings()
    api_key = getattr(settings, "_resolved_api_key", None)
    if not api_key:
        frappe.throw("OpenAI API key is not configured for AI reports.")  # noqa: TRY003

    days_int = _coerce_days(days)
    service_user = settings.resolve_service_user()
    context = collect_admin_context(days=days_int, run_as=service_user)
    template = custom_prompt or DEFAULT_PROMPT
    prompt = _format_prompt(template, context)

    report = frappe.new_doc("AI Report")
    report.update(
        {
            "title": title or f"AI Admin Summary ({days_int}d)",
            "report_type": "Summary" if custom_prompt is None else "Custom Prompt",
            "status": "Running",
            "prompt": prompt,
            "context_json": json.dumps(context, indent=2, default=str),
            "model_used": settings.openai_model,
        }
    )
    report.insert(ignore_permissions=True)
    frappe.db.commit()

    try:
        output = generate_completion(
            api_key=api_key,
            model=settings.openai_model,
            system_prompt=SYSTEM_PROMPT,
            user_prompt=prompt,
            timeout=DEFAULT_TIMEOUT,
        )
    except Exception as exc:  # pragma: no cover - network failures
        report.status = "Failed"
        report.error_message = str(exc)
        report.generated_on = now_datetime()
        report.save(ignore_permissions=True)
        frappe.db.commit()
        raise

    report.status = "Success"
    report.generated_on = now_datetime()
    report.ai_output = output
    report.save(ignore_permissions=True)
    frappe.db.commit()

    return {
        "report_name": report.name,
        "output": output,
        "context": context,
    }
