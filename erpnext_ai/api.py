from __future__ import annotations

from typing import Any, Dict, Optional

import frappe

from erpnext_ai.erpnext_ai.services.admin_summary import collect_admin_context
from erpnext_ai.erpnext_ai.services import chat
from erpnext_ai.erpnext_ai.services.report_runner import generate_admin_report


@frappe.whitelist()
def get_admin_context(days: int = 30) -> Dict[str, Any]:
    if not frappe.has_permission("AI Report", "read"):
        frappe.throw("You are not permitted to view AI context.", frappe.PermissionError)  # noqa: TRY003
    try:
        days_int = int(days)
    except (TypeError, ValueError):
        days_int = 30
    return collect_admin_context(days=days_int)


@frappe.whitelist()
def generate_admin_summary(
    title: Optional[str] = None,
    custom_prompt: Optional[str] = None,
    days: int = 30,
) -> Dict[str, Any]:
    return generate_admin_report(title=title, custom_prompt=custom_prompt, days=days)


@frappe.whitelist()
def create_ai_conversation(title: Optional[str] = None, include_context: int = 1) -> Dict[str, Any]:
    if not frappe.has_permission("AI Conversation", "create"):
        frappe.throw("You are not permitted to start AI conversations.", frappe.PermissionError)  # noqa: TRY003
    return chat.create_conversation(title=title, include_context=bool(include_context))


@frappe.whitelist()
def get_ai_conversation(conversation_name: str) -> Dict[str, Any]:
    return chat.get_conversation(conversation_name)


@frappe.whitelist()
def append_ai_message(
    conversation_name: str,
    role: str,
    content: str,
    context_json: Optional[str] = None,
) -> Dict[str, Any]:
    return chat.append_conversation_message(conversation_name, role, content, context_json=context_json)


@frappe.whitelist()
def send_ai_message(conversation_name: str, message: str, days: int = 30) -> Dict[str, Any]:
    return chat.send_message(conversation_name, message, days=days)
