from __future__ import annotations

from typing import Any, Dict, Optional

import frappe

from erpnext_ai.erpnext_ai.services.admin_summary import collect_admin_context
from erpnext_ai.erpnext_ai.services import chat
from erpnext_ai.erpnext_ai.services.item_creator import create_items, preview_item_batch, preview_item_series
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


@frappe.whitelist()
def preview_item_creation(
    raw_text: str,
    item_group: str,
    stock_uom: str,
    use_ai: int = 0,
    max_items: int = 200,
) -> Dict[str, Any]:
    return preview_item_batch(
        raw_text=raw_text,
        item_group=item_group,
        stock_uom=stock_uom,
        use_ai=bool(int(use_ai or 0)),
        max_items=max_items,
    )


@frappe.whitelist()
def create_items_from_preview(items: Any, create_disabled: int = 1) -> Dict[str, Any]:
    payload = frappe.parse_json(items) if items is not None else []
    if not isinstance(payload, list):
        frappe.throw("Items payload must be a list.", frappe.ValidationError)  # noqa: TRY003
    return create_items(items=payload, create_disabled=bool(int(create_disabled or 0)))


@frappe.whitelist()
def preview_item_creation_series(
    item_group: str,
    stock_uom: str,
    name_prefix: str,
    code_prefix: str,
    count: int = 20,
    start: int = 1,
    pad: int = 0,
) -> Dict[str, Any]:
    return preview_item_series(
        item_group=item_group,
        stock_uom=stock_uom,
        name_prefix=name_prefix,
        code_prefix=code_prefix,
        count=count,
        start=start,
        pad=pad,
    )
