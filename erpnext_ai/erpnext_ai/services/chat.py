from __future__ import annotations

import json
from typing import Any, Dict

import frappe

from erpnext_ai.erpnext_ai.doctype.ai_conversation.ai_conversation import AIConversation
from erpnext_ai.erpnext_ai.doctype.ai_settings.ai_settings import AISettings, DEFAULT_TIMEOUT
from .admin_summary import collect_admin_context
from .openai_client import generate_completion


CHAT_CONTEXT_PROMPT = (
    "ERP Context Snapshot (JSON). Use these figures to give precise answers about user counts, stock levels, "
    "financial totals, and active staff. If a value is missing, explain what additional data is required."
)


def _coerce_days(days: Any) -> int:
    try:
        return int(days)
    except (TypeError, ValueError):
        return 30


def _serialize_conversation(doc: AIConversation) -> Dict[str, Any]:
    return {
        "name": doc.name,
        "title": doc.title,
        "status": doc.status,
        "include_context": doc.include_context,
        "last_interaction": doc.last_interaction,
        "messages": [
            {
                "name": msg.name,
                "role": msg.role,
                "content": msg.content,
                "context_json": msg.context_json,
                "creation": msg.creation,
            }
            for msg in (doc.messages or [])
        ],
    }


def create_conversation(title: str | None = None, include_context: bool = True) -> Dict[str, Any]:
    doc = frappe.new_doc("AI Conversation")
    doc.title = title or "ERPNext AI Assistant"
    doc.include_context = 1 if include_context else 0
    doc.user = frappe.session.user
    doc.insert()
    frappe.db.commit()
    return _serialize_conversation(doc)


def get_conversation(conversation_name: str) -> Dict[str, Any]:
    doc = frappe.get_doc("AI Conversation", conversation_name)
    doc.check_permission("read")
    return _serialize_conversation(doc)


def append_conversation_message(
    conversation_name: str,
    role: str,
    content: str,
    context_json: str | None = None,
) -> Dict[str, Any]:
    doc = frappe.get_doc("AI Conversation", conversation_name)
    doc.check_permission("write")
    doc.append_message(role, content, context_json=context_json)
    doc.save(ignore_permissions=True)
    frappe.db.commit()
    return _serialize_conversation(doc)


def _build_context_hint(context: Dict[str, Any]) -> str | None:
    """Return supplemental guidance when minimal transactional data is available."""
    metrics = context.get("metrics") or {}
    pending = context.get("pending") or {}
    core = context.get("core_overview") or {}
    finance = context.get("finance") or {}
    inventory = context.get("inventory") or {}
    people = context.get("people") or {}
    records = context.get("records") or {}

    def _non_zero(value: Any) -> bool:
        if isinstance(value, dict):
            return any(_non_zero(v) for v in value.values())
        if isinstance(value, (list, tuple, set)):
            return any(_non_zero(v) for v in value)
        try:
            return bool(float(value))
        except (TypeError, ValueError):
            return bool(value)

    if any(_non_zero(entry) for entry in metrics.values()):
        return None
    if any(_non_zero(entry) for entry in pending.values()):
        return None
    if _non_zero(core):
        return None
    if _non_zero(finance):
        return None
    if _non_zero(inventory):
        return None
    if _non_zero(people):
        return None
    if _non_zero(records):
        return None
    if context.get("top_customers"):
        return None

    return (
        "ERP ma'lumotlar omborida tanlangan davr uchun tasdiqlangan tranzaksiyalar topilmadi. "
        "Foydalanuvchi savoliga do'stona ohangda javob bering va kerak bo'lsa yangi hujjatlar "
        "kiritish yoki mavjudlarini tekshirish bo'yicha tavsiyalar bering."
    )


def _format_context_summary(context: Dict[str, Any], days: int, prompt: str | None = None) -> str:
    meta = context.get("meta") or {}
    core = dict(context.get("core_overview") or {})
    system_user_details = core.pop("system_user_details", [])
    metrics = context.get("metrics") or {}
    finance = context.get("finance") or {}
    inventory = dict(context.get("inventory") or {})
    top_stock_items = inventory.pop("top_items", [])
    pending = context.get("pending") or {}
    people = dict(context.get("people") or {})
    active_employee_details = people.pop("active_employee_details", [])
    top_customers = context.get("top_customers") or []
    records = context.get("records") or {}
    record_users = records.get("users") or []
    recent_customers = records.get("customers") or []
    recent_items = records.get("items") or []
    recent_sales = records.get("sales_invoices") or []
    recent_purchases = records.get("purchase_invoices") or []
    warehouse_directory = records.get("warehouses") or []

    lines = [
        f"ERP tizimingiz bo'yicha so'nggi {days} kunlik qisqa sharh:",
        "",
    ]

    if prompt:
        lines.append(f"Savolingiz: “{prompt}”")
        lines.append("")

    def _format_value(label: str, value: Any) -> str | None:
        nice_label = label.replace("_", " ").title()
        if isinstance(value, dict):
            count = value.get("count") or value.get("accounts")
            amount = value.get("amount") or value.get("balance") or value.get("stock_value")
            qty = value.get("total_qty")
            if count or amount or qty:
                parts: list[str] = []
                if count is not None:
                    parts.append(f"{int(count)} ta")
                if qty is not None:
                    parts.append(f"miqdor {qty}")
                if amount is not None:
                    parts.append(f"summa {float(amount):,.2f}")
                return f"- {nice_label}: " + ", ".join(parts)
            return None
        try:
            if float(value):
                return f"- {nice_label}: {float(value):,.2f}"
        except (TypeError, ValueError):
            if value:
                return f"- {nice_label}: {value}"
        return None

    if core:
        core_lines = [_format_value(label, value) or f"- {label.replace('_', ' ').title()}: {value}" for label, value in core.items()]
        if any(core_lines):
            lines.append("Asosiy ko'rsatkichlar:")
            lines.extend(filter(None, core_lines))
            lines.append("")
    if system_user_details:
        lines.append("Faol tizim foydalanuvchilari (so'nggi kirish va email bo'yicha):")
        for user in system_user_details:
            display_name = user.get("full_name") or user.get("user_id")
            extras: list[str] = []
            email = user.get("email")
            if email and email != user.get("user_id"):
                extras.append(email)
            last_login = user.get("last_login")
            if last_login:
                extras.append(f"oxirgi kirish {last_login}")
            suffix = f" ({', '.join(extras)})" if extras else ""
            lines.append(f"- {display_name}{suffix}")
        lines.append("")
    if record_users:
        lines.append("Kengaytirilgan tizim foydalanuvchilari ro'yxati:")
        for user in record_users[:10]:
            display_name = user.get("full_name") or user.get("user_id")
            details: list[str] = []
            if user.get("email"):
                details.append(user["email"])
            if user.get("mobile_no"):
                details.append(user["mobile_no"])
            if not user.get("enabled"):
                details.append("faolsiz")
            last_login = user.get("last_login")
            if last_login:
                details.append(f"oxirgi kirish {last_login}")
            lines.append(f"- {display_name} ({', '.join(details)})")
        if len(record_users) > 10:
            lines.append(f"- ... jami {len(record_users)} ta tizim foydalanuvchisi mavjud.")
        lines.append("")

    if metrics:
        metric_lines = []
        for label, value in metrics.items():
            entry = _format_value(label, value)
            if entry:
                metric_lines.append(entry)
        if metric_lines:
            lines.append("Tranzaksiyalar statistikasi:")
            lines.extend(metric_lines)
            lines.append("")

    if finance:
        has_finance = any(
            [
                finance.get("receivables"),
                finance.get("payables"),
                (finance.get("cash_bank") or {}).get("balance"),
            ]
        )
        lines.append("Moliya holati:")
        cash_bank = finance.get("cash_bank") or {}
        if cash_bank and (cash_bank.get("accounts") or cash_bank.get("balance")):
            lines.append(
                f"- Naqd va bank hisoblari ({cash_bank.get('accounts', 0)} ta): balans {cash_bank.get('balance', 0):,.2f}"
            )
        lines.append(f"- Qarzdorlik (mijozlar): {finance.get('receivables', 0):,.2f}")
        lines.append(f"- Kreditorlik (ta'minotchilar): {finance.get('payables', 0):,.2f}")
        lines.append("")

    if inventory:
        inv_lines = [
            f"- Turli tovarlar soni: {inventory.get('distinct_items', 0)}",
            f"- Umumiy miqdor: {inventory.get('total_qty', 0)}",
            f"- Taxminiy qiymat: {inventory.get('stock_value', 0):,.2f}",
        ]
        lines.append("Ombor qoldiqlari:")
        lines.extend(inv_lines)
        lines.append("")
    if top_stock_items:
        lines.append("Eng katta aylanmadagi tovarlar:")
        for item in top_stock_items:
            name = item.get("item_name") or item.get("item_code")
            qty = float(item.get("total_qty") or 0.0)
            value = float(item.get("stock_value") or 0.0)
            warehouses = int(item.get("warehouse_count") or 0)
            parts = [f"{qty:,.2f} birlik", f"qiymat {value:,.2f}"]
            if warehouses:
                parts.append(f"{warehouses} ta omborda")
            lines.append(f"- {name}: {', '.join(parts)}")
        lines.append("")

    if pending:
        pending_lines = [f"- {label.replace('_', ' ').title()}: {value}" for label, value in pending.items()]
        lines.append("Jarayondagi obyektlar:")
        lines.extend(pending_lines)
        lines.append("")

    if people:
        lines.append("HR ko'rsatkichlari:")
        lines.extend(f"- {label.replace('_', ' ').title()}: {value}" for label, value in people.items())
        lines.append("")
    if active_employee_details:
        lines.append("Faol xodimlar:")
        for employee in active_employee_details:
            name = employee.get("employee_name") or employee.get("employee")
            descriptors: list[str] = []
            if employee.get("designation"):
                descriptors.append(employee["designation"])
            if employee.get("department"):
                descriptors.append(employee["department"])
            if employee.get("company"):
                descriptors.append(employee["company"])
            if employee.get("branch"):
                descriptors.append(employee["branch"])
            suffix = f" ({', '.join(descriptors)})" if descriptors else ""
            lines.append(f"- {name}{suffix}")
        lines.append("")

    if top_customers:
        lines.append("Top mijozlar:")
        for cust in top_customers:
            lines.append(
                f"- {cust.get('customer')}: {cust.get('invoice_count', 0)} ta hisob-faktura, {cust.get('amount', 0):,.2f}"
            )
        lines.append("")

    if recent_customers:
        lines.append("So'nggi faol mijozlar (yakuniy o'zgarish va aloqa ma'lumotlari):")
        for cust in recent_customers[:5]:
            display = cust.get("customer_name") or cust.get("name")
            contact_bits = []
            if cust.get("mobile_no"):
                contact_bits.append(cust["mobile_no"])
            if cust.get("email_id"):
                contact_bits.append(cust["email_id"])
            territory = cust.get("territory")
            if territory:
                contact_bits.append(territory)
            suffix = f" ({', '.join(contact_bits)})" if contact_bits else ""
            lines.append(f"- {display}{suffix}")
        lines.append("")

    if recent_items:
        lines.append("So'nggi yangilangan tovarlar:")
        for item in recent_items[:5]:
            title = item.get("item_name") or item.get("item_code")
            group = item.get("item_group")
            parts = [item.get("stock_uom")]
            if group:
                parts.append(group)
            lines.append(f"- {title} ({', '.join(filter(None, parts))})")
        lines.append("")

    if recent_sales:
        lines.append("Yaqinda tasdiqlangan savdo hisob-fakturalari:")
        for inv in recent_sales[:5]:
            lines.append(
                f"- {inv.get('name')} ({inv.get('customer_name')}): {inv.get('total', 0):,.2f}, qarzdorlik {inv.get('outstanding', 0):,.2f}"
            )
        lines.append("")

    if recent_purchases:
        lines.append("Yaqinda tasdiqlangan xarid hisob-fakturalari:")
        for pinv in recent_purchases[:5]:
            lines.append(
                f"- {pinv.get('name')} ({pinv.get('supplier_name')}): {pinv.get('total', 0):,.2f}, qarzdorlik {pinv.get('outstanding', 0):,.2f}"
            )
        lines.append("")

    if warehouse_directory:
        lines.append("Mavjud omborlar:")
        for wh in warehouse_directory[:5]:
            label = wh.get("warehouse_name") or wh.get("warehouse")
            company = wh.get("company")
            lines.append(f"- {label} ({company})")
        lines.append("")

    suggestions: list[str] = []
    prompt_lower = (prompt or "").lower()
    if "user" in prompt_lower:
        suggestions.append("Foydalanuvchilar ro'yxatini ko'rish uchun Desk → Users → User sahifasini tekshirib, faollashtirilgan foydalanuvchilarni tasdiqlang.")
    if "hisobot" in prompt_lower or "report" in prompt_lower:
        suggestions.append("Analytics → Dashboard yoki ERPNext'ning standarts hisobotlarini ochib, kerakli bo'limni PDF/Excel ko'rinishida eksport qiling.")
    if not suggestions:
        suggestions.extend(
            [
                "Yangi ma'lumotlar kiritib, keyinroq yana so'rang — AI avtomatik ravishda yangilangan ko'rsatkichlarni oladi.",
                "Ma'lum bir modul bo'yicha savolingiz bo'lsa, nomini aytib so'rang (masalan, “Stock'dagi qoldiq qanday?”).",
            ]
        )

    lines.append("Tavsiyalar:")
    for item in suggestions:
        lines.append(f"- {item}")
    lines.append("")

    lines.append("Qo'shimcha savollar bo'lsa, davom eting — tizim ma'lumotlariga tayangan holda yordam berishga tayyorman.")
    return "\n".join(line for line in lines if line.strip() != "" or line == "")


def send_message(conversation_name: str, content: str, days: int = 30) -> Dict[str, Any]:
    doc = frappe.get_doc("AI Conversation", conversation_name)
    doc.check_permission("write")

    if doc.status == "Closed":
        frappe.throw("Conversation is closed.")  # noqa: TRY003

    days_int = _coerce_days(days)

    settings = AISettings.get_settings()
    api_key = getattr(settings, "_resolved_api_key", None)
    if not api_key:
        frappe.throw("OpenAI API key is not configured.")  # noqa: TRY003

    content = (content or "").strip()
    if not content:
        frappe.throw("Cannot send an empty message.")  # noqa: TRY003

    # Append user message
    doc.append_message("user", content)

    base_payload = [dict(message) for message in doc.to_message_payload()]

    service_user = settings.resolve_service_user()

    context_data: Dict[str, Any] | None = None
    context_json = None
    context_message = None
    context_hint = None
    if doc.include_context:
        context_data = collect_admin_context(days=days_int, run_as=service_user)
        context_json = json.dumps(context_data, indent=2, default=str)
        context_hint = _build_context_hint(context_data)

        context_content = f"{CHAT_CONTEXT_PROMPT}\n{context_json}"
        if context_hint:
            context_content = f"{context_content}\n\nNote: {context_hint}"
        context_message = {"role": "system", "content": context_content}

    def build_payload(include_context: bool, limit_to_last_user: bool) -> list[dict]:
        messages = [dict(msg) for msg in base_payload]
        if limit_to_last_user:
            system_msg = messages[0] if messages else {"role": "system", "content": "You are an ERPNext copilot."}
            last_user = next((dict(msg) for msg in reversed(messages) if msg.get("role") == "user"), None)
            payload = [dict(system_msg)]
            if include_context and context_message:
                payload.append(dict(context_message))
            if last_user:
                payload.append(dict(last_user))
            return payload

        if include_context and context_message:
            messages.insert(1, dict(context_message))
        return messages

    attempts = [
        {"include_context": bool(context_message), "limit_to_last_user": False},
        {"include_context": False, "limit_to_last_user": False},
        {"include_context": bool(context_message), "limit_to_last_user": True},
        {"include_context": False, "limit_to_last_user": True},
    ]

    reply_text = ""
    used_context = False
    last_exception: Exception | None = None

    for attempt in attempts:
        payload = build_payload(attempt["include_context"], attempt["limit_to_last_user"])
        try:
            reply = generate_completion(
                api_key=api_key,
                model=settings.openai_model,
                messages=payload,
                timeout=DEFAULT_TIMEOUT,
                temperature=0.2,
                max_completion_tokens=700,
            )
        except Exception as exc:
            last_exception = exc
            continue

        reply_text = (reply or "").strip()
        if reply_text:
            used_context = attempt["include_context"] and context_message is not None
            break

    if not reply_text:
        if last_exception is not None:
            doc.save(ignore_permissions=True)
            frappe.db.commit()
            raise last_exception

        summary = None
        if context_data:
            try:
                summary = _format_context_summary(context_data, days_int, prompt=content)
            except Exception:
                summary = None

        if summary:
            reply_text = summary
        else:
            frappe.log_error("OpenAI returned empty completion for AI chat.", "AI Chat Empty Response")
            reply_text = "I could not generate a response right now. Please try again in a moment."

    doc.append_message("assistant", reply_text, context_json=context_json if used_context else None)
    doc.save(ignore_permissions=True)
    frappe.db.commit()

    return _serialize_conversation(doc)
