from __future__ import annotations

import base64
import binascii
from dataclasses import dataclass, field
import hashlib
import json
import os
from pathlib import Path
from typing import List, Optional, Set


def _parse_int_set(value: str) -> Set[int]:
    result: Set[int] = set()
    for part in value.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            result.add(int(part))
        except ValueError:
            continue
    return result


def _parse_fields(value: str) -> List[str]:
    cleaned = value.strip()
    if not cleaned:
        return []
    if cleaned.startswith("["):
        try:
            data = json.loads(cleaned)
        except json.JSONDecodeError:
            return []
        return [str(item) for item in data if isinstance(item, str)]
    return [field.strip() for field in cleaned.split(",") if field.strip()]


def _derive_encryption_key(source: str) -> bytes:
    digest = hashlib.sha256(source.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest)


@dataclass
class ReportSettings:
    resource: str = "Sales Order"
    fields: List[str] = field(
        default_factory=lambda: [
            "name",
            "customer_name",
            "transaction_date",
            "grand_total",
            "per_delivered",
        ]
    )
    limit: int = 5
    order_by: str = "transaction_date desc"


@dataclass
class OrderSettings:
    target_doctype: str = "Lead"
    lead_source: str = "Telegram Bot"
    territory: Optional[str] = None
    status: str = "Lead"
    attach_order_photo: bool = True


@dataclass
class BotConfig:
    token: str
    admin_ids: Set[int]
    frappe_base_url: str
    request_timeout: float
    db_path: Path
    encryption_key: bytes
    report: ReportSettings
    order: OrderSettings
    bot_name: str = "sales_bot"
    verification_endpoint: str = "/api/method/frappe.auth.get_logged_user"


def load_bot_config() -> BotConfig:
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is required to run the Telegram bot.")

    admin_ids = _parse_int_set(os.getenv("TELEGRAM_ADMIN_IDS", ""))

    base_url = os.getenv("FRAPPE_BASE_URL", "").rstrip("/")
    if not base_url:
        raise RuntimeError("FRAPPE_BASE_URL must point to your ERPNext site (e.g., https://example.com).")

    timeout_raw = os.getenv("ERP_REQUEST_TIMEOUT", "10")
    try:
        request_timeout = float(timeout_raw)
    except ValueError:
        request_timeout = 10.0

    db_path = Path(os.getenv("TELEGRAM_BOT_DB_PATH", "telegram_bot.sqlite3")).expanduser()

    # Encryption key precedence: explicit base64 key > token derived fallback.
    encryption_env = os.getenv("BOT_ENCRYPTION_KEY")
    encryption_key: bytes
    if encryption_env:
        candidate = encryption_env.strip().encode("utf-8")
        try:
            decoded = base64.urlsafe_b64decode(candidate)
        except (binascii.Error, ValueError):
            encryption_key = _derive_encryption_key(encryption_env)
        else:
            if len(decoded) != 32:
                encryption_key = _derive_encryption_key(encryption_env)
            else:
                encryption_key = candidate
    else:
        encryption_key = _derive_encryption_key(token)

    report_settings = ReportSettings()
    resource_override = os.getenv("TELEGRAM_REPORT_RESOURCE")
    if resource_override:
        report_settings.resource = resource_override.strip()
    fields_override = _parse_fields(os.getenv("TELEGRAM_REPORT_FIELDS", ""))
    if fields_override:
        report_settings.fields = fields_override
    limit_raw = os.getenv("TELEGRAM_REPORT_LIMIT")
    if limit_raw:
        try:
            report_settings.limit = max(1, int(limit_raw))
        except ValueError:
            pass
    order_by_override = os.getenv("TELEGRAM_REPORT_ORDER_BY")
    if order_by_override:
        report_settings.order_by = order_by_override.strip()

    order_settings = OrderSettings()
    doc_override = os.getenv("TELEGRAM_ORDER_TARGET_DOCTYPE")
    if doc_override:
        order_settings.target_doctype = doc_override.strip()
    lead_source = os.getenv("TELEGRAM_ORDER_SOURCE")
    if lead_source:
        order_settings.lead_source = lead_source.strip()
    territory = os.getenv("TELEGRAM_ORDER_TERRITORY")
    if territory:
        order_settings.territory = territory.strip()
    status = os.getenv("TELEGRAM_ORDER_STATUS")
    if status:
        order_settings.status = status.strip()
    attach_photo_env = os.getenv("TELEGRAM_ORDER_ATTACH_PHOTO")
    if attach_photo_env:
        order_settings.attach_order_photo = attach_photo_env.strip().lower() in {"1", "true", "yes"}

    bot_name = os.getenv("TELEGRAM_BOT_NAME", "sales_bot").strip() or "sales_bot"
    verify_endpoint = os.getenv("FRAPPE_VERIFICATION_ENDPOINT", "/api/method/frappe.auth.get_logged_user")

    return BotConfig(
        token=token,
        admin_ids=admin_ids,
        frappe_base_url=base_url,
        request_timeout=request_timeout,
        db_path=db_path,
        encryption_key=encryption_key,
        report=report_settings,
        order=order_settings,
        bot_name=bot_name,
        verification_endpoint=verify_endpoint,
    )
