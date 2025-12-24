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
            "AI Item Creation is disabled. Enable it in AI Settings before creating Items.",
            frappe.PermissionError,
        )


def _coerce_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


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
    defaults = ItemDefaults(item_group=(item_group or "").strip(), stock_uom=(stock_uom or "").strip())
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
            base_code = _default_item_code(item_name)
            candidate_code = _ensure_unique_item_code(base_code, used_codes)
            if candidate_code != base_code:
                issues.append("Item code adjusted to be unique.")

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
        item_group = (entry.get("item_group") or "").strip()
        stock_uom = (entry.get("stock_uom") or "").strip()

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
            doc.insert()
        except Exception as exc:  # pragma: no cover - depends on ERPNext validations
            failed.append({"item_code": item_code, "item_name": item_name, "error": str(exc)})
            continue

        created.append(doc.name)

    frappe.db.commit()
    return {"created": created, "skipped": skipped, "failed": failed}
