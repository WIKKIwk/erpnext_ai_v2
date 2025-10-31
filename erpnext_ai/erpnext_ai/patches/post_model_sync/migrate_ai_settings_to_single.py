"""Migrate legacy AI Settings records into new single DocType."""
from __future__ import annotations

import frappe

FIELDS = [
    "api_provider",
    "openai_model",
    "service_user",
    "openai_api_key",
]


def execute() -> None:
    if not frappe.db.table_exists("tabAI Settings"):
        frappe.reload_doctype("AI Settings")
        frappe.get_single("AI Settings").save(ignore_permissions=True)
        return

    existing = frappe.db.get_all(
        "AI Settings",
        fields=FIELDS,
        order_by="creation asc",
        limit=1,
    )

    frappe.reload_doctype("AI Settings")
    doc = frappe.get_single("AI Settings")
    if existing:
        doc.update({field: existing[0].get(field) for field in FIELDS})
    doc.save(ignore_permissions=True)
