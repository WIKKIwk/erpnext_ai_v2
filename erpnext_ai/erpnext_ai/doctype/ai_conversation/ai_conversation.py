from __future__ import annotations

from typing import List

import frappe
from frappe.model.document import Document
from frappe.utils import now_datetime


class AIConversation(Document):
    def before_insert(self) -> None:
        if not self.user:
            self.user = frappe.session.user
        self.last_interaction = now_datetime()

    def on_change(self) -> None:
        self.last_interaction = now_datetime()

    def append_message(self, role: str, content: str, context_json: str | None = None) -> None:
        self.append(
            "messages",
            {
                "role": role,
                "content": content,
                "context_json": context_json,
            },
        )

    def to_message_payload(self) -> List[dict]:
        payload: List[dict] = []
        system_prompt = self.system_prompt or "You are an ERPNext copilot."
        payload.append({"role": "system", "content": system_prompt})

        for msg in self.messages or []:
            payload.append({"role": msg.role, "content": msg.content})

        return payload

