from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Tuple

import frappe

from erpnext_ai.erpnext_ai.doctype.ai_settings.ai_settings import AISettings, DEFAULT_TIMEOUT
from .llm_client import generate_completion as generate_llm_completion


MAX_ITEM_BATCH_SIZE = 200
ITEM_CODE_MAX_LENGTH = 140
AI_CREATED_FIELD = "erpnext_ai_created"
ALLOWED_UPDATE_FIELDS = {"item_name", "item_group", "stock_uom", "disabled", "description"}


@dataclass(frozen=True)
class ItemDefaults:
    item_group: str
    stock_uom: str


def ensure_item_creation_enabled() -> None:
    try:
        settings = frappe.get_single("AI Settings")
    except Exception as exc:  # pragma: no cover - defensive
        raise frappe.DoesNotExistError("AI Settings not found.") from exc

    if not getattr(settings, "allow_item_creation", 0):
        frappe.throw(
            "AI Item operations are disabled. Enable them in AI Settings before continuing.",
            frappe.PermissionError,
        )


def _coerce_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _resolve_link_value(doctype: str, value: str) -> str:
    cleaned = (value or "").strip()
    if not cleaned:
        return ""
    if frappe.db.exists(doctype, cleaned):
        return cleaned

    table = f"tab{doctype}"
    rows = frappe.db.sql(
        f"select name from `{table}` where lower(name)=lower(%s) limit 1",
        (cleaned,),
        as_list=True,
    )
    if rows and rows[0] and rows[0][0]:
        return rows[0][0]
    return cleaned


def _has_ai_created_field() -> bool:
    cached = getattr(frappe.flags, "erpnext_ai_has_item_flag", None)
    if cached is None:
        cached = AI_CREATED_FIELD in frappe.db.get_table_columns("Item")
        frappe.flags.erpnext_ai_has_item_flag = cached
    return bool(cached)


def _normalise_item_codes(values: Any) -> List[str]:
    if values is None:
        return []
    if isinstance(values, (list, tuple, set)):
        raw_values = list(values)
    elif isinstance(values, str):
        raw_values = re.split(r"[,\n]+", values)
    else:
        raw_values = [values]

    seen: set[str] = set()
    result: List[str] = []
    for entry in raw_values:
        value = str(entry or "").strip()
        if not value:
            continue
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def _series_item_codes(code_prefix: str, count: int, start: int, pad: int) -> List[str]:
    count_int = _coerce_int(count, 0)
    start_int = _coerce_int(start, 1)
    pad_int = max(_coerce_int(pad, 0), 0)

    if count_int < 1:
        return []

    def _format_number(value: int) -> str:
        if pad_int:
            return f"{value:0{pad_int}d}"
        return str(value)

    prefix = (code_prefix or "").strip()
    return [f"{prefix}{_format_number(start_int + offset)}" for offset in range(count_int)]


def _lookup_item(item_code: str) -> Optional[Dict[str, Any]]:
    if not item_code:
        return None
    fields = ["name", "item_code", "item_name"]
    if _has_ai_created_field():
        fields.append(AI_CREATED_FIELD)

    data = frappe.db.get_value("Item", {"item_code": item_code}, fields, as_dict=True)
    if data:
        return data
    return frappe.db.get_value("Item", item_code, fields, as_dict=True)


def _is_ai_created(item_row: Optional[Dict[str, Any]]) -> bool:
    if not item_row or not _has_ai_created_field():
        return False
    return bool(item_row.get(AI_CREATED_FIELD))


def _validate_item_updates(updates: Any) -> Dict[str, Any]:
    if updates is None:
        frappe.throw("Updates are required.", frappe.ValidationError)  # noqa: TRY003
    if isinstance(updates, str):
        try:
            updates = json.loads(updates)
        except json.JSONDecodeError as exc:
            frappe.throw(f"Invalid updates JSON: {exc}", frappe.ValidationError)  # noqa: TRY003

    if not isinstance(updates, dict):
        frappe.throw("Updates must be a JSON object.", frappe.ValidationError)  # noqa: TRY003

    cleaned: Dict[str, Any] = {}
    for field, value in updates.items():
        if field not in ALLOWED_UPDATE_FIELDS:
            continue
        if field == "item_name":
            name_value = str(value or "").strip()
            if not name_value:
                frappe.throw("Item Name cannot be empty.", frappe.ValidationError)  # noqa: TRY003
            cleaned[field] = name_value
        elif field == "item_group":
            group_value = _resolve_link_value("Item Group", str(value or "").strip())
            if not frappe.db.exists("Item Group", group_value):
                frappe.throw("Invalid Item Group.", frappe.ValidationError)  # noqa: TRY003
            cleaned[field] = group_value
        elif field == "stock_uom":
            uom_value = _resolve_link_value("UOM", str(value or "").strip())
            if not frappe.db.exists("UOM", uom_value):
                frappe.throw("Invalid Stock UOM.", frappe.ValidationError)  # noqa: TRY003
            cleaned[field] = uom_value
        elif field == "disabled":
            cleaned[field] = 1 if bool(value) else 0
        elif field == "description":
            cleaned[field] = str(value or "")

    if not cleaned:
        frappe.throw("No supported fields to update.", frappe.ValidationError)  # noqa: TRY003
    return cleaned


def _clean_line(line: str) -> str:
    stripped = (line or "").strip()
    if not stripped:
        return ""
    if stripped.startswith("#"):
        return ""
    return stripped


def _parse_line(line: str) -> Tuple[str | None, str | None]:
    """Return (item_code, item_name) parsed from a single line."""
    cleaned = _clean_line(line)
    if not cleaned:
        return None, None

    for sep in ("\t", "|", ",", ";"):
        if sep in cleaned:
            parts = [part.strip() for part in cleaned.split(sep)]
            if len(parts) >= 2 and parts[0] and parts[1]:
                return parts[0], parts[1]

    match = re.match(r"^\s*([A-Za-z0-9][A-Za-z0-9._/-]{1,})\s*[-–—]\s*(.+?)\s*$", cleaned)
    if match:
        code = match.group(1).strip()
        name = match.group(2).strip()
        if code and name:
            return code, name

    return None, cleaned


def _parse_items_heuristic(raw_text: str) -> List[Dict[str, str]]:
    items: List[Dict[str, str]] = []
    for line in (raw_text or "").splitlines():
        item_code, item_name = _parse_line(line)
        if not item_name:
            continue
        payload: Dict[str, str] = {"item_name": item_name}
        if item_code:
            payload["item_code"] = item_code
        items.append(payload)
    return items


def _extract_json_array(text: str) -> Any:
    candidate = (text or "").strip()
    if not candidate:
        raise ValueError("Empty AI response")

    if candidate.startswith("```"):
        candidate = re.sub(r"^```(?:json)?", "", candidate, flags=re.IGNORECASE).strip()
        candidate = re.sub(r"```$", "", candidate).strip()

    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        start = candidate.find("[")
        end = candidate.rfind("]")
        if start == -1 or end == -1 or end <= start:
            raise
        return json.loads(candidate[start : end + 1])


def _parse_items_with_ai(raw_text: str, max_items: int) -> List[Dict[str, str]]:
    settings = AISettings.get_settings()
    api_key = getattr(settings, "_resolved_api_key", None)
    if not api_key:
        frappe.throw(f"{settings.api_provider} API key is not configured.", frappe.ValidationError)  # noqa: TRY003

    system_prompt = (
        "You convert messy product lists into structured JSON for ERPNext Item creation.\n"
        "Return ONLY a JSON array. No markdown, no extra text.\n"
        "Each element is an object with:\n"
        '- "item_name" (required)\n'
        '- "item_code" (optional)\n'
        f"Limit the output to at most {max_items} items.\n"
        "Do not invent categories, UOMs, prices, or any extra fields.\n"
    )

    user_prompt = f"Input:\n{raw_text}\n\nOutput JSON array now."

    response = generate_llm_completion(
        provider=settings.api_provider,
        api_key=api_key,
        model=settings.openai_model,
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        temperature=0,
        max_completion_tokens=900,
        timeout=DEFAULT_TIMEOUT,
    )

    parsed = _extract_json_array(response)
    if not isinstance(parsed, list):
        raise ValueError("AI response must be a JSON array")

    items: List[Dict[str, str]] = []
    for entry in parsed[:max_items]:
        if not isinstance(entry, dict):
            continue
        item_name = (entry.get("item_name") or "").strip()
        if not item_name:
            continue
        item_code = (entry.get("item_code") or "").strip()
        payload: Dict[str, str] = {"item_name": item_name}
        if item_code:
            payload["item_code"] = item_code
        items.append(payload)

    if not items:
        raise ValueError("AI did not return any valid items")
    return items


def _default_item_code(item_name: str) -> str:
    base = re.sub(r"\s+", " ", (item_name or "").strip())
    base = re.sub(r"[^A-Za-z0-9]+", "-", base).strip("-")
    if not base:
        base = "ITEM"
    base = base[:ITEM_CODE_MAX_LENGTH].strip("-")
    return base.upper()


def _item_code_exists(item_code: str) -> bool:
    if not item_code:
        return False
    if frappe.db.exists("Item", item_code):
        return True
    return bool(frappe.db.exists("Item", {"item_code": item_code}))


def _ensure_unique_item_code(item_code: str, used_codes: set[str]) -> str:
    base = (item_code or "").strip() or "ITEM"
    base = base[:ITEM_CODE_MAX_LENGTH]
    candidate = base
    suffix = 1
    while candidate in used_codes or _item_code_exists(candidate):
        suffix += 1
        suffix_token = f"-{suffix}"
        truncated = base[: ITEM_CODE_MAX_LENGTH - len(suffix_token)].rstrip("-")
        candidate = f"{truncated}{suffix_token}"
    used_codes.add(candidate)
    return candidate


def _validate_defaults(defaults: ItemDefaults) -> List[str]:
    issues: List[str] = []
    if not defaults.item_group or not frappe.db.exists("Item Group", defaults.item_group):
        issues.append("Invalid Item Group.")
    if not defaults.stock_uom or not frappe.db.exists("UOM", defaults.stock_uom):
        issues.append("Invalid Stock UOM.")
    return issues


def preview_item_batch(
    *,
    raw_text: str,
    item_group: str,
    stock_uom: str,
    use_ai: bool = False,
    max_items: int = MAX_ITEM_BATCH_SIZE,
) -> Dict[str, Any]:
    ensure_item_creation_enabled()

    if not frappe.has_permission("Item", "create"):
        frappe.throw("You are not permitted to create Items.", frappe.PermissionError)  # noqa: TRY003

    max_items_int = min(max(_coerce_int(max_items, MAX_ITEM_BATCH_SIZE), 1), MAX_ITEM_BATCH_SIZE)
    defaults = ItemDefaults(
        item_group=_resolve_link_value("Item Group", (item_group or "").strip()),
        stock_uom=_resolve_link_value("UOM", (stock_uom or "").strip()),
    )
    default_issues = _validate_defaults(defaults)
    if default_issues:
        frappe.throw(" ".join(default_issues), frappe.ValidationError)  # noqa: TRY003

    warnings: List[str] = []
    parsed_items: List[Dict[str, str]]
    if use_ai:
        try:
            parsed_items = _parse_items_with_ai(raw_text, max_items_int)
        except Exception as exc:
            warnings.append(f"AI parsing failed; falling back to simple parsing. ({exc})")
            parsed_items = _parse_items_heuristic(raw_text)
    else:
        parsed_items = _parse_items_heuristic(raw_text)

    if not parsed_items:
        frappe.throw("No items found in input.", frappe.ValidationError)  # noqa: TRY003

    parsed_items = parsed_items[:max_items_int]
    used_codes: set[str] = set()

    rows: List[Dict[str, Any]] = []
    for idx, entry in enumerate(parsed_items, start=1):
        item_name = (entry.get("item_name") or "").strip()
        requested_code = (entry.get("item_code") or "").strip()

        issues: List[str] = []
        if not item_name:
            issues.append("Missing item_name.")
        candidate_code = requested_code[:ITEM_CODE_MAX_LENGTH].strip() if requested_code else ""
        exists = False
        if candidate_code:
            if candidate_code in used_codes:
                issues.append("Duplicate item_code in input.")
            used_codes.add(candidate_code)
            exists = _item_code_exists(candidate_code)
            if exists:
                issues.append("Item already exists.")
        else:
            candidate_code = _default_item_code(item_name)
            if candidate_code in used_codes:
                issues.append("Duplicate item in input.")
            used_codes.add(candidate_code)
            exists = _item_code_exists(candidate_code)
            if exists:
                issues.append("Item already exists.")

        rows.append(
            {
                "idx": idx,
                "item_code": candidate_code,
                "item_name": item_name,
                "item_group": defaults.item_group,
                "stock_uom": defaults.stock_uom,
                "exists": bool(exists),
                "issues": issues,
            }
        )

    return {
        "defaults": {"item_group": defaults.item_group, "stock_uom": defaults.stock_uom},
        "warnings": warnings,
        "items": rows,
    }


def preview_item_series(
    *,
    item_group: str,
    stock_uom: str,
    name_prefix: str,
    code_prefix: str,
    count: int = 20,
    start: int = 1,
    pad: int = 0,
    max_items: int = MAX_ITEM_BATCH_SIZE,
) -> Dict[str, Any]:
    count_int = _coerce_int(count, 20)
    start_int = _coerce_int(start, 1)
    pad_int = max(_coerce_int(pad, 0), 0)
    max_items_int = min(max(_coerce_int(max_items, MAX_ITEM_BATCH_SIZE), 1), MAX_ITEM_BATCH_SIZE)

    if count_int < 1:
        frappe.throw("Count must be at least 1.", frappe.ValidationError)  # noqa: TRY003
    if count_int > max_items_int:
        frappe.throw(f"Count cannot exceed {max_items_int}.", frappe.ValidationError)  # noqa: TRY003

    name_prefix_value = (name_prefix or "").strip()
    code_prefix_value = (code_prefix or "").strip()
    if not name_prefix_value:
        frappe.throw("Name prefix is required.", frappe.ValidationError)  # noqa: TRY003
    if not code_prefix_value:
        frappe.throw("Code prefix is required.", frappe.ValidationError)  # noqa: TRY003

    def _format_number(value: int) -> str:
        if pad_int:
            return f"{value:0{pad_int}d}"
        return str(value)

    lines: List[str] = []
    for offset in range(count_int):
        number = _format_number(start_int + offset)
        item_name = f"{name_prefix_value}{number}"
        item_code = f"{code_prefix_value}{number}"
        lines.append(f"{item_code} - {item_name}")

    return preview_item_batch(
        raw_text="\n".join(lines),
        item_group=item_group,
        stock_uom=stock_uom,
        use_ai=False,
        max_items=max_items_int,
    )


def create_items(
    *,
    items: Sequence[Dict[str, Any]],
    create_disabled: bool = True,
) -> Dict[str, Any]:
    ensure_item_creation_enabled()

    if not frappe.has_permission("Item", "create"):
        frappe.throw("You are not permitted to create Items.", frappe.PermissionError)  # noqa: TRY003

    created: List[str] = []
    skipped: List[Dict[str, Any]] = []
    failed: List[Dict[str, Any]] = []

    for entry in items[:MAX_ITEM_BATCH_SIZE]:
        item_code = (entry.get("item_code") or "").strip()
        item_name = (entry.get("item_name") or "").strip()
        item_group = _resolve_link_value("Item Group", (entry.get("item_group") or "").strip())
        stock_uom = _resolve_link_value("UOM", (entry.get("stock_uom") or "").strip())

        if not item_code or not item_name:
            failed.append({"item_code": item_code, "item_name": item_name, "error": "Missing item_code or item_name"})
            continue
        if _item_code_exists(item_code):
            skipped.append({"item_code": item_code, "item_name": item_name, "reason": "Already exists"})
            continue
        if not frappe.db.exists("Item Group", item_group):
            failed.append({"item_code": item_code, "item_name": item_name, "error": "Invalid Item Group"})
            continue
        if not frappe.db.exists("UOM", stock_uom):
            failed.append({"item_code": item_code, "item_name": item_name, "error": "Invalid Stock UOM"})
            continue

        try:
            doc = frappe.new_doc("Item")
            doc.item_code = item_code
            doc.item_name = item_name
            doc.item_group = item_group
            doc.stock_uom = stock_uom
            if hasattr(doc, "disabled") and create_disabled:
                doc.disabled = 1
            if _has_ai_created_field():
                doc.set(AI_CREATED_FIELD, 1)
            doc.insert()
        except Exception as exc:  # pragma: no cover - depends on ERPNext validations
            failed.append({"item_code": item_code, "item_name": item_name, "error": str(exc)})
            continue

        created.append(doc.name)

    frappe.db.commit()
    return {"created": created, "skipped": skipped, "failed": failed}


def preview_item_deletion(item_codes: Any) -> Dict[str, Any]:
    ensure_item_creation_enabled()

    if not frappe.has_permission("Item", "delete"):
        frappe.throw("You are not permitted to delete Items.", frappe.PermissionError)  # noqa: TRY003

    codes = _normalise_item_codes(item_codes)
    rows: List[Dict[str, Any]] = []
    for idx, code in enumerate(codes, start=1):
        item_row = _lookup_item(code)
        if not item_row:
            rows.append(
                {
                    "idx": idx,
                    "item_code": code,
                    "item_name": "",
                    "ai_created": False,
                    "can_delete": False,
                    "reason": "Item not found.",
                }
            )
            continue

        ai_created = _is_ai_created(item_row)
        reason = "" if ai_created else "Not created by ERPNext AI."
        rows.append(
            {
                "idx": idx,
                "item_code": item_row.get("item_code") or code,
                "item_name": item_row.get("item_name") or "",
                "ai_created": ai_created,
                "can_delete": ai_created,
                "reason": reason,
            }
        )

    return {"items": rows}


def preview_item_deletion_series(
    *,
    code_prefix: str,
    count: int = 20,
    start: int = 1,
    pad: int = 0,
) -> Dict[str, Any]:
    codes = _series_item_codes(code_prefix=code_prefix, count=count, start=start, pad=pad)
    if not codes:
        frappe.throw("Count must be at least 1.", frappe.ValidationError)  # noqa: TRY003
    return preview_item_deletion(codes)


def delete_items(
    item_codes: Any,
    allow_unmarked_codes: Optional[Sequence[str]] = None,
) -> Dict[str, Any]:
    ensure_item_creation_enabled()

    if not frappe.has_permission("Item", "delete"):
        frappe.throw("You are not permitted to delete Items.", frappe.PermissionError)  # noqa: TRY003

    deleted: List[str] = []
    skipped: List[Dict[str, Any]] = []
    failed: List[Dict[str, Any]] = []

    codes = _normalise_item_codes(item_codes)
    allow_set = set(_normalise_item_codes(allow_unmarked_codes)) if allow_unmarked_codes else set()
    for code in codes:
        item_row = _lookup_item(code)
        if not item_row:
            skipped.append({"item_code": code, "reason": "Item not found"})
            continue
        if not _is_ai_created(item_row):
            item_code_value = (item_row.get("item_code") or code or "").strip()
            name_value = str(item_row.get("name") or "").strip()
            if not allow_set or (item_code_value not in allow_set and name_value not in allow_set):
                skipped.append({"item_code": code, "reason": "Not created by ERPNext AI"})
                continue
        try:
            frappe.delete_doc("Item", item_row["name"], ignore_permissions=False)
        except Exception as exc:  # pragma: no cover - depends on ERPNext validations
            failed.append({"item_code": code, "error": str(exc)})
            continue
        deleted.append(code)

    frappe.db.commit()
    return {"deleted": deleted, "skipped": skipped, "failed": failed}


def preview_item_update(item_codes: Any, updates: Any) -> Dict[str, Any]:
    ensure_item_creation_enabled()

    if not frappe.has_permission("Item", "write"):
        frappe.throw("You are not permitted to edit Items.", frappe.PermissionError)  # noqa: TRY003

    cleaned_updates = _validate_item_updates(updates)
    codes = _normalise_item_codes(item_codes)
    rows: List[Dict[str, Any]] = []
    for idx, code in enumerate(codes, start=1):
        item_row = _lookup_item(code)
        if not item_row:
            rows.append(
                {
                    "idx": idx,
                    "item_code": code,
                    "item_name": "",
                    "ai_created": False,
                    "can_update": False,
                    "reason": "Item not found.",
                }
            )
            continue
        ai_created = _is_ai_created(item_row)
        reason = "" if ai_created else "Not created by ERPNext AI."
        rows.append(
            {
                "idx": idx,
                "item_code": item_row.get("item_code") or code,
                "item_name": item_row.get("item_name") or "",
                "ai_created": ai_created,
                "can_update": ai_created,
                "reason": reason,
            }
        )

    return {"items": rows, "updates": cleaned_updates}


def preview_item_update_series(
    *,
    code_prefix: str,
    updates: Any,
    count: int = 20,
    start: int = 1,
    pad: int = 0,
) -> Dict[str, Any]:
    codes = _series_item_codes(code_prefix=code_prefix, count=count, start=start, pad=pad)
    if not codes:
        frappe.throw("Count must be at least 1.", frappe.ValidationError)  # noqa: TRY003
    return preview_item_update(codes, updates)


def apply_item_update(item_codes: Any, updates: Any) -> Dict[str, Any]:
    ensure_item_creation_enabled()

    if not frappe.has_permission("Item", "write"):
        frappe.throw("You are not permitted to edit Items.", frappe.PermissionError)  # noqa: TRY003

    cleaned_updates = _validate_item_updates(updates)
    updated: List[str] = []
    skipped: List[Dict[str, Any]] = []
    failed: List[Dict[str, Any]] = []

    codes = _normalise_item_codes(item_codes)
    for code in codes:
        item_row = _lookup_item(code)
        if not item_row:
            skipped.append({"item_code": code, "reason": "Item not found"})
            continue
        if not _is_ai_created(item_row):
            skipped.append({"item_code": code, "reason": "Not created by ERPNext AI"})
            continue
        try:
            doc = frappe.get_doc("Item", item_row["name"])
            for field, value in cleaned_updates.items():
                doc.set(field, value)
            doc.save()
        except Exception as exc:  # pragma: no cover - depends on ERPNext validations
            failed.append({"item_code": code, "error": str(exc)})
            continue
        updated.append(code)

    frappe.db.commit()
    return {"updated": updated, "skipped": skipped, "failed": failed}
