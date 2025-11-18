"""Background tasks for the ERPNext AI app.

This module intentionally keeps dependencies light so that it keeps working
even when optional services (external LLMs, email, etc.) are unavailable.
"""

from __future__ import annotations

import json
from typing import Dict

import frappe
from frappe import _
from frappe.utils import format_datetime, now_datetime


def generate_daily_admin_summary() -> None:
    """Collect a handful of business metrics and surface them to the AI team.

    The goal is resilience: if any of the source DocTypes is missing on a site
    we simply skip that metric and continue. A summary note is appended to the
    *AI Settings* document and a realtime notification is pushed to the user
    configured there (defaults to Administrator).
    """

    logger = frappe.logger("erpnext_ai.tasks", allow_site=True)

    try:
        settings = frappe.get_single("AI Settings")
    except frappe.DoesNotExistError:
        logger.info("AI Settings not found; skipping daily summary generation.")
        return
    except Exception:  # pragma: no cover - scheduler safety net
        logger.exception("Failed to load AI Settings; skipping daily summary.")
        return

    metrics = _collect_metrics(logger)
    if not metrics:
        logger.info("No metrics collected; skipping daily summary output.")
        return

    message = _render_summary(metrics)
    logger.info("Daily AI summary generated: %s", json.dumps(metrics))

    _record_comment(settings.name, settings.service_user or "Administrator", message, logger)
    _push_realtime_update(settings.service_user or "Administrator", metrics, message, logger)


def _collect_metrics(logger) -> Dict[str, int]:
    """Gather a small set of operational numbers without failing the scheduler."""

    metric_specs = [
        (
            "open_sales_invoices",
            "Sales Invoice",
            [("docstatus", "=", 1), ("outstanding_amount", ">", 0)],
        ),
        (
            "pending_sales_orders",
            "Sales Order",
            [("docstatus", "=", 1), ("status", "not in", ("Completed", "Closed"))],
        ),
        (
            "overdue_purchase_invoices",
            "Purchase Invoice",
            [("docstatus", "=", 1), ("outstanding_amount", ">", 0)],
        ),
        (
            "open_support_issues",
            "Issue",
            [("status", "not in", ("Closed", "Resolved"))],
        ),
        (
            "overdue_tasks",
            "Task",
            [("status", "in", ("Open", "Overdue", "Working"))],
        ),
    ]

    metrics: Dict[str, int] = {}
    for key, doctype, filters in metric_specs:
        try:
            metrics[key] = frappe.db.count(doctype, filters=filters)
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("Failed to collect %s for %s: %s", key, doctype, exc)
            metrics[key] = 0

    return metrics


def _render_summary(metrics: Dict[str, int]) -> str:
    timestamp = format_datetime(now_datetime(), "yyyy-MM-dd HH:mm")
    lines = [
        _("Daily AI Admin Summary ({0})").format(timestamp),
        "",
        _("Open Sales Invoices (Outstanding) : {0}").format(metrics["open_sales_invoices"]),
        _("Pending Sales Orders             : {0}").format(metrics["pending_sales_orders"]),
        _("Overdue Purchase Invoices       : {0}").format(metrics["overdue_purchase_invoices"]),
        _("Open Support Issues             : {0}").format(metrics["open_support_issues"]),
        _("Overdue / Working Tasks         : {0}").format(metrics["overdue_tasks"]),
    ]
    return "\n".join(lines)


def _record_comment(reference_name: str, owner: str, content: str, logger) -> None:
    try:
        frappe.get_doc(
            {
                "doctype": "Comment",
                "comment_type": "Info",
                "reference_doctype": "AI Settings",
                "reference_name": reference_name,
                "content": content,
                "owner": owner,
            }
        ).insert(ignore_permissions=True, ignore_links=True)
    except Exception:  # pragma: no cover - defensive
        logger.exception("Failed to append AI summary comment")


def _push_realtime_update(user: str, metrics: Dict[str, int], message: str, logger) -> None:
    try:
        frappe.publish_realtime(
            event="erpnext_ai_daily_summary",
            message={"metrics": metrics, "text": message},
            user=user,
            after_commit=True,
        )
    except Exception:  # pragma: no cover - defensive
        logger.warning("Unable to push realtime AI summary update", exc_info=True)
