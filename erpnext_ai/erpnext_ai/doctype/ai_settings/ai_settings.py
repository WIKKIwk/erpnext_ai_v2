from __future__ import annotations

import os

import frappe
from frappe.model.document import Document


DEFAULT_PROMPT = """You are an assistant that summarises ERPNext activity for administrators.
Use the context JSON to highlight noteworthy KPIs, anomalies, and actionable insights.
Return Markdown with clear headings and bullet points.

Context JSON:
{context}
"""

DEFAULT_OPENAI_MODEL = "gpt-4o"
DEFAULT_TIMEOUT = 60


class AISettings(Document):
    def validate(self) -> None:
        self.api_provider = self.api_provider or "OpenAI"
        if not self.openai_model or self.openai_model in {"gpt-5", "gpt-5-mini"}:
            self.openai_model = DEFAULT_OPENAI_MODEL
        service_user = getattr(self, "service_user", None)
        if not service_user:
            self.service_user = "Administrator"

        if not self.resolve_api_key():
            frappe.throw("Enter your OpenAI API key to activate the assistant.")

    def resolve_api_key(self) -> str | None:
        env_key = os.getenv("OPENAI_API_KEY") or frappe.conf.get("openai_api_key")
        return env_key or self.openai_api_key

    def resolve_service_user(self) -> str:
        return self.service_user or "Administrator"

    @staticmethod
    def get_settings() -> "AISettings":
        settings = frappe.get_single("AI Settings")
        resolved_key = settings.resolve_api_key()
        if not resolved_key:
            frappe.throw("Configure an OpenAI API key in AI Settings to use the assistant.")

        settings._resolved_api_key = resolved_key  # type: ignore[attr-defined]
        if not settings.api_provider:
            settings.api_provider = "OpenAI"
        if not settings.openai_model or settings.openai_model in {"gpt-5", "gpt-5-mini"}:
            settings.openai_model = DEFAULT_OPENAI_MODEL
        if not getattr(settings, "service_user", None):
            settings.service_user = "Administrator"

        return settings

    @staticmethod
    def get_service_user(default: str = "Administrator") -> str:
        try:
            doc = frappe.get_single("AI Settings")
        except Exception:
            return default
        user = getattr(doc, "service_user", None)
        return user or default
