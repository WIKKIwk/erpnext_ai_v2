"""Add AI-created flag to Item for ERPNext AI actions."""
from __future__ import annotations

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_field


def execute() -> None:
    if not frappe.db.table_exists("tabItem"):
        return

    fieldname = "erpnext_ai_created"
    if frappe.db.exists("Custom Field", {"dt": "Item", "fieldname": fieldname}):
        if fieldname in frappe.db.get_table_columns("Item"):
            return
    else:
        create_custom_field(
            "Item",
            {
                "fieldname": fieldname,
                "label": "Created by ERPNext AI",
                "fieldtype": "Check",
                "default": 0,
                "read_only": 1,
                "hidden": 1,
                "no_copy": 1,
                "insert_after": "disabled",
            },
        )

    if fieldname not in frappe.db.get_table_columns("Item"):
        frappe.reload_doctype("Item")
