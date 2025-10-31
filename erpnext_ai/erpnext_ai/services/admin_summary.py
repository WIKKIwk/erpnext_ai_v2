from __future__ import annotations

from contextlib import contextmanager
from datetime import date, datetime, timedelta
from typing import Any, Dict, List

import frappe


@contextmanager
def _impersonate(user: str | None):
    original_user = getattr(frappe.session, "user", None)
    target = user or original_user
    if target and original_user != target:
        frappe.set_user(target)
    try:
        yield
    finally:
        if original_user and getattr(frappe.session, "user", None) != original_user:
            frappe.set_user(original_user)


def _default_dates(days: int) -> tuple[date, date]:
    end_date = date.today()
    start_date = end_date - timedelta(days=days)
    return start_date, end_date


def _currency(value: Any) -> float:
    if value is None:
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _collect_total(doctype: str, amount_field: str, date_field: str, start: date) -> Dict[str, Any]:
    if not frappe.db.table_exists(doctype):
        return {"count": 0, "amount": 0.0}

    res = frappe.db.sql(
        f"""
        SELECT
            COUNT(name) AS count,
            COALESCE(SUM({amount_field}), 0) AS total
        FROM `tab{doctype}`
        WHERE docstatus = 1
          AND {date_field} >= %s
        """,
        start,
        as_dict=True,
    )
    if not res:
        return {"count": 0, "amount": 0.0}
    row = res[0]
    return {
        "count": int(row.get("count") or 0),
        "amount": _currency(row.get("total")),
    }


def _collect_open_count(doctype: str, status_field: str, closed_status: str) -> int:
    if not frappe.db.table_exists(doctype):
        return 0
    return frappe.db.count(
        doctype,
        filters={
            status_field: ("!=", closed_status),
            "docstatus": ("<", 2),
        },
    )


def _top_customers(limit: int, start: date) -> List[Dict[str, Any]]:
    if not frappe.db.table_exists("Sales Invoice"):
        return []

    rows = frappe.db.sql(
        """
        SELECT
            customer_name AS customer,
            COUNT(name) AS invoice_count,
            COALESCE(SUM(base_grand_total), 0) AS total
        FROM `tabSales Invoice`
        WHERE docstatus = 1
          AND posting_date >= %s
        GROUP BY customer_name
        ORDER BY total DESC
        LIMIT %s
        """,
        (start, limit),
        as_dict=True,
    )
    return [
        {
            "customer": row.get("customer") or row.get("customer_name"),
            "invoice_count": int(row.get("invoice_count") or 0),
            "amount": _currency(row.get("total")),
        }
        for row in rows
    ]


def _safe_count(doctype: str, *, filters: Dict[str, Any] | None = None) -> int:
    if not frappe.db.table_exists(doctype):
        return 0
    return frappe.db.count(doctype, filters=filters or {})


def _list_system_users(limit: int = 10) -> List[Dict[str, Any]]:
    if not frappe.db.table_exists("User"):
        return []

    rows = frappe.db.sql(
        """
        SELECT
            name,
            full_name,
            email,
            last_login,
            creation
        FROM `tabUser`
        WHERE enabled = 1
          AND user_type = 'System User'
        ORDER BY IFNULL(last_login, creation) DESC
        LIMIT %s
        """,
        limit,
        as_dict=True,
    )

    details: List[Dict[str, Any]] = []
    for row in rows:
        last_login = row.get("last_login")
        details.append(
            {
                "user_id": row.get("name"),
                "full_name": row.get("full_name") or row.get("name"),
                "email": row.get("email"),
                "last_login": last_login.isoformat() if hasattr(last_login, "isoformat") else last_login,
            }
        )
    return details


def _system_user_directory(limit: int = 100) -> List[Dict[str, Any]]:
    if not frappe.db.table_exists("User"):
        return []

    rows = frappe.db.sql(
        """
        SELECT
            name,
            full_name,
            email,
            mobile_no,
            last_login,
            creation,
            enabled,
            user_type
        FROM `tabUser`
        WHERE user_type = 'System User'
        ORDER BY enabled DESC, IFNULL(last_login, creation) DESC
        LIMIT %s
        """,
        limit,
        as_dict=True,
    )
    directory: List[Dict[str, Any]] = []
    for row in rows:
        directory.append(
            {
                "user_id": row.get("name"),
                "full_name": row.get("full_name") or row.get("name"),
                "email": row.get("email"),
                "mobile_no": row.get("mobile_no"),
                "enabled": int(row.get("enabled") or 0),
                "last_login": _as_iso(row.get("last_login")),
                "created_on": _as_iso(row.get("creation")),
            }
        )
    return directory


def _as_iso(value: Any) -> Any:
    if hasattr(value, "isoformat"):
        # Handles datetime/date/timedelta compatible objects
        return value.isoformat()  # type: ignore[no-any-return]
    return value


def _recent_customers(limit: int = 20) -> List[Dict[str, Any]]:
    if not frappe.db.table_exists("Customer"):
        return []

    rows = frappe.db.sql(
        """
        SELECT
            name,
            customer_name,
            customer_group,
            customer_type,
            territory,
            mobile_no,
            email_id,
            disabled,
            modified
        FROM `tabCustomer`
        ORDER BY modified DESC
        LIMIT %s
        """,
        limit,
        as_dict=True,
    )
    return [
        {
            "name": row.get("name"),
            "customer_name": row.get("customer_name"),
            "customer_group": row.get("customer_group"),
            "customer_type": row.get("customer_type"),
            "territory": row.get("territory"),
            "mobile_no": row.get("mobile_no"),
            "email_id": row.get("email_id"),
            "disabled": int(row.get("disabled") or 0),
            "modified": _as_iso(row.get("modified")),
        }
        for row in rows
    ]


def _recent_items(limit: int = 20) -> List[Dict[str, Any]]:
    if not frappe.db.table_exists("Item"):
        return []

    rows = frappe.db.sql(
        """
        SELECT
            name,
            item_name,
            item_group,
            stock_uom,
            is_stock_item,
            disabled,
            modified
        FROM `tabItem`
        ORDER BY modified DESC
        LIMIT %s
        """,
        limit,
        as_dict=True,
    )
    return [
        {
            "item_code": row.get("name"),
            "item_name": row.get("item_name"),
            "item_group": row.get("item_group"),
            "stock_uom": row.get("stock_uom"),
            "is_stock_item": int(row.get("is_stock_item") or 0),
            "disabled": int(row.get("disabled") or 0),
            "modified": _as_iso(row.get("modified")),
        }
        for row in rows
    ]


def _warehouse_directory(limit: int = 50) -> List[Dict[str, Any]]:
    if not frappe.db.table_exists("Warehouse"):
        return []

    rows = frappe.db.sql(
        """
        SELECT
            name,
            warehouse_name,
            company,
            is_group,
            disabled,
            parent_warehouse,
            creation,
            modified
        FROM `tabWarehouse`
        ORDER BY is_group DESC, warehouse_name ASC
        LIMIT %s
        """,
        limit,
        as_dict=True,
    )
    return [
        {
            "warehouse": row.get("name"),
            "warehouse_name": row.get("warehouse_name"),
            "company": row.get("company"),
            "parent_warehouse": row.get("parent_warehouse"),
            "is_group": int(row.get("is_group") or 0),
            "disabled": int(row.get("disabled") or 0),
            "created_on": _as_iso(row.get("creation")),
            "modified": _as_iso(row.get("modified")),
        }
        for row in rows
    ]


def _recent_sales_invoices(limit: int = 15) -> List[Dict[str, Any]]:
    if not frappe.db.table_exists("Sales Invoice"):
        return []

    rows = frappe.db.sql(
        """
        SELECT
            name,
            customer_name,
            posting_date,
            base_grand_total,
            outstanding_amount,
            status,
            modified
        FROM `tabSales Invoice`
        WHERE docstatus = 1
        ORDER BY posting_date DESC, modified DESC
        LIMIT %s
        """,
        limit,
        as_dict=True,
    )
    return [
        {
            "name": row.get("name"),
            "customer_name": row.get("customer_name"),
            "posting_date": _as_iso(row.get("posting_date")),
            "total": _currency(row.get("base_grand_total")),
            "outstanding": _currency(row.get("outstanding_amount")),
            "status": row.get("status"),
            "modified": _as_iso(row.get("modified")),
        }
        for row in rows
    ]


def _recent_purchase_invoices(limit: int = 15) -> List[Dict[str, Any]]:
    if not frappe.db.table_exists("Purchase Invoice"):
        return []

    rows = frappe.db.sql(
        """
        SELECT
            name,
            supplier_name,
            posting_date,
            base_grand_total,
            outstanding_amount,
            status,
            modified
        FROM `tabPurchase Invoice`
        WHERE docstatus = 1
        ORDER BY posting_date DESC, modified DESC
        LIMIT %s
        """,
        limit,
        as_dict=True,
    )
    return [
        {
            "name": row.get("name"),
            "supplier_name": row.get("supplier_name"),
            "posting_date": _as_iso(row.get("posting_date")),
            "total": _currency(row.get("base_grand_total")),
            "outstanding": _currency(row.get("outstanding_amount")),
            "status": row.get("status"),
            "modified": _as_iso(row.get("modified")),
        }
        for row in rows
    ]


def _stock_snapshot() -> Dict[str, Any]:
    if not frappe.db.table_exists("Bin"):
        return {"distinct_items": 0, "total_qty": 0.0, "stock_value": 0.0}

    row = frappe.db.sql(
        """
        SELECT
            COUNT(DISTINCT item_code) AS items,
            COALESCE(SUM(actual_qty), 0) AS qty,
            COALESCE(SUM(stock_value), 0) AS value
        FROM `tabBin`
        """,
        as_dict=True,
    )[0]
    return {
        "distinct_items": int(row.get("items") or 0),
        "total_qty": float(row.get("qty") or 0.0),
        "stock_value": _currency(row.get("value")),
    }


def _top_stock_items(limit: int = 10) -> List[Dict[str, Any]]:
    if not frappe.db.table_exists("Bin"):
        return []

    rows = frappe.db.sql(
        """
        SELECT
            b.item_code AS item_code,
            IFNULL(i.item_name, b.item_code) AS item_name,
            COUNT(DISTINCT b.warehouse) AS warehouse_count,
            COALESCE(SUM(b.actual_qty), 0) AS total_qty,
            COALESCE(SUM(b.stock_value), 0) AS total_value
        FROM `tabBin` b
        LEFT JOIN `tabItem` i ON i.name = b.item_code
        GROUP BY b.item_code, item_name
        ORDER BY total_value DESC, total_qty DESC
        LIMIT %s
        """,
        limit,
        as_dict=True,
    )

    return [
        {
            "item_code": row.get("item_code"),
            "item_name": row.get("item_name"),
            "total_qty": float(row.get("total_qty") or 0.0),
            "stock_value": _currency(row.get("total_value")),
            "warehouse_count": int(row.get("warehouse_count") or 0),
        }
        for row in rows
    ]


def _cash_position() -> Dict[str, Any]:
    if not frappe.db.table_exists("Account"):
        return {"accounts": 0, "balance": 0.0}

    account_filters = {
        "account_type": ("in", ["Cash", "Bank"]),
        "is_group": 0,
        "disabled": 0,
    }

    if not frappe.db.table_exists("GL Entry"):
        return {
            "accounts": frappe.db.count("Account", filters=account_filters),
            "balance": 0.0,
        }

    row = frappe.db.sql(
        """
        SELECT
            COUNT(DISTINCT acc.name) AS accounts,
            COALESCE(SUM(CASE WHEN gle.docstatus = 1 THEN gle.debit - gle.credit ELSE 0 END), 0) AS balance
        FROM `tabAccount` acc
        LEFT JOIN `tabGL Entry` gle ON gle.account = acc.name
        WHERE acc.account_type IN ('Cash', 'Bank')
          AND acc.is_group = 0
          AND acc.disabled = 0
        """,
        as_dict=True,
    )[0]

    return {
        "accounts": int(row.get("accounts") or 0),
        "balance": _currency(row.get("balance")),
    }


def _receivable_payable(start: date) -> Dict[str, float]:
    totals = {"receivables": 0.0, "payables": 0.0}
    if frappe.db.table_exists("Sales Invoice"):
        value = frappe.db.sql(
            """
            SELECT COALESCE(SUM(outstanding_amount), 0)
            FROM `tabSales Invoice`
            WHERE docstatus = 1 AND posting_date >= %s
            """,
            start,
        )
        totals["receivables"] = _currency(value[0][0]) if value else 0.0

    if frappe.db.table_exists("Purchase Invoice"):
        value = frappe.db.sql(
            """
            SELECT COALESCE(SUM(outstanding_amount), 0)
            FROM `tabPurchase Invoice`
            WHERE docstatus = 1 AND posting_date >= %s
            """,
            start,
        )
        totals["payables"] = _currency(value[0][0]) if value else 0.0

    return totals


def _active_employee_details(limit: int = 10) -> List[Dict[str, Any]]:
    if not frappe.db.table_exists("Employee"):
        return []

    rows = frappe.db.sql(
        """
        SELECT
            name,
            employee_name,
            designation,
            department,
            company,
            branch,
            modified,
            creation
        FROM `tabEmployee`
        WHERE status = 'Active'
        ORDER BY IFNULL(modified, creation) DESC
        LIMIT %s
        """,
        limit,
        as_dict=True,
    )

    return [
        {
            "employee": row.get("name"),
            "employee_name": row.get("employee_name") or row.get("name"),
            "designation": row.get("designation"),
            "department": row.get("department"),
            "company": row.get("company"),
            "branch": row.get("branch"),
        }
        for row in rows
    ]


def _hr_overview() -> Dict[str, Any]:
    employees = _safe_count("Employee", filters={"status": "Active"})
    open_leaves = 0
    if frappe.db.table_exists("Leave Application"):
        open_leaves = frappe.db.count(
            "Leave Application",
            filters={
                "status": ("in", ["Open", "Approved"]),
                "docstatus": 1,
            },
        )
    return {
        "active_employees": employees,
        "open_leave_applications": open_leaves,
        "active_employee_details": _active_employee_details(limit=10),
    }


def collect_admin_context(days: int = 30, *, run_as: str | None = None) -> Dict[str, Any]:
    if run_as is None:
        try:
            from erpnext_ai.erpnext_ai.doctype.ai_settings.ai_settings import AISettings

            run_as = AISettings.get_service_user()
        except Exception:
            run_as = "Administrator"

    with _impersonate(run_as):
        start, end = _default_dates(days)

        receivable_payable = _receivable_payable(start)
        system_user_details = _list_system_users(limit=12)
        inventory_snapshot = _stock_snapshot()
        inventory_snapshot["top_items"] = _top_stock_items(limit=10)

        return {
            "meta": {
                "period_days": days,
                "period_start": start.isoformat(),
                "period_end": end.isoformat(),
            },
            "core_overview": {
                "system_users": _safe_count("User", filters={"enabled": 1, "user_type": "System User"}),
                "website_users": _safe_count("User", filters={"enabled": 1, "user_type": "Website User"}),
                "customers": _safe_count("Customer"),
                "suppliers": _safe_count("Supplier"),
                "items": _safe_count("Item"),
                "warehouses": _safe_count("Warehouse"),
                "companies": _safe_count("Company"),
                "system_user_details": system_user_details,
            },
            "metrics": {
                "sales_invoices": _collect_total("Sales Invoice", "base_grand_total", "posting_date", start),
                "sales_orders": _collect_total("Sales Order", "base_grand_total", "transaction_date", start),
                "purchase_invoices": _collect_total("Purchase Invoice", "base_grand_total", "posting_date", start),
                "purchase_orders": _collect_total("Purchase Order", "base_grand_total", "transaction_date", start),
                "delivery_notes": _collect_total("Delivery Note", "base_grand_total", "posting_date", start),
                "open_support_tickets": _collect_open_count("Issue", "status", "Closed"),
            },
            "finance": {
                "cash_bank": _cash_position(),
                "receivables": receivable_payable["receivables"],
                "payables": receivable_payable["payables"],
            },
            "inventory": inventory_snapshot,
            "top_customers": _top_customers(5, start),
            "pending": {
                "quotations": _collect_total("Quotation", "base_grand_total", "transaction_date", start)["count"],
                "purchase_orders": _collect_total("Purchase Order", "base_grand_total", "transaction_date", start)["count"],
                "projects": frappe.db.count("Project", filters={"status": ("in", ["Open", "Hold"])}),
            },
            "people": _hr_overview(),
            "records": {
                "users": _system_user_directory(limit=150),
                "customers": _recent_customers(limit=25),
                "items": _recent_items(limit=25),
                "warehouses": _warehouse_directory(limit=50),
                "sales_invoices": _recent_sales_invoices(limit=20),
                "purchase_invoices": _recent_purchase_invoices(limit=20),
            },
        }
