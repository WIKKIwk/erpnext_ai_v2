from __future__ import annotations

import frappe


def ensure_role() -> None:
    if frappe.db.exists("Role", "AI Manager"):
        return

    role = frappe.get_doc(
        {
            "doctype": "Role",
            "role_name": "AI Manager",
            "desk_access": 1,
            "is_custom": 1,
        }
    )
    role.insert(ignore_permissions=True)
    frappe.db.commit()


def ensure_single_ai_settings() -> None:
    frappe.reload_doc("erpnext_ai", "doctype", "ai_settings")

    if frappe.db.table_exists("tabAI Settings"):
        frappe.db.sql("DROP TABLE `tabAI Settings`")
        frappe.db.commit()

    frappe.db.set_value("DocType", "AI Settings", "issingle", 1)
    frappe.clear_cache(doctype="AI Settings")

    doc = frappe.get_single("AI Settings")
    if not doc.api_provider:
        frappe.db.set_single_value("AI Settings", "api_provider", "OpenAI")
    if not doc.openai_model:
        frappe.db.set_single_value("AI Settings", "openai_model", "gpt-5-mini")



def hide_legacy_workspace() -> None:
    if frappe.db.exists("Workspace", "AI Command Center"):
        frappe.db.set_value("Workspace", "AI Command Center", "is_hidden", 1)
        frappe.db.set_value("Workspace", "AI Command Center", "public", 0)


def run() -> None:
    ensure_role()
    ensure_single_ai_settings()
    hide_legacy_workspace()
