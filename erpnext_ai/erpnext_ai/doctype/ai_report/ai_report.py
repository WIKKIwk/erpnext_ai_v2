from __future__ import annotations

import json

import frappe
from frappe.model.document import Document
from frappe.utils import now_datetime


class AIReport(Document):
    def before_insert(self) -> None:
        if not self.generated_on:
            self.generated_on = now_datetime()

    def validate(self) -> None:
        if self.context_json:
            try:
                json.loads(self.context_json)
            except json.JSONDecodeError as exc:
                frappe.throw(f"Context JSON is invalid: {exc}")  # noqa: TRY003

