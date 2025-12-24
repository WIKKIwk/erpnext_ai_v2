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
DEFAULT_GEMINI_MODEL = "gemini-2.5-flash"
DEFAULT_TIMEOUT = 60


class AISettings(Document):
    @staticmethod
    def normalise_provider(value: str | None) -> str:
        provider = (value or "OpenAI").strip()
        lower = provider.lower()
        if lower == "gemini":
            return "Gemini"
        if lower == "openai":
            return "OpenAI"
        return provider or "OpenAI"

    def validate(self) -> None:
        self.api_provider = self.normalise_provider(self.api_provider)
        self.openai_model = self.resolve_model()
        service_user = getattr(self, "service_user", None)
        if not service_user:
            self.service_user = "Administrator"

        if not self.resolve_api_key():
            frappe.throw(f"Enter your {self.api_provider} API key to activate the assistant.")

    def resolve_api_key(self) -> str | None:
        provider = self.normalise_provider(self.api_provider)
        if provider == "Gemini":
            env_key = (
                os.getenv("GEMINI_API_KEY")
                or os.getenv("GOOGLE_API_KEY")
                or frappe.conf.get("gemini_api_key")
                or frappe.conf.get("google_api_key")
            )
            if env_key:
                return env_key

            if getattr(self, "gemini_api_key", None):
                try:
                    return self.get_password("gemini_api_key")
                except Exception:
                    return self.gemini_api_key

            return None

        env_key = os.getenv("OPENAI_API_KEY") or frappe.conf.get("openai_api_key")
        if env_key:
            return env_key

        if getattr(self, "openai_api_key", None):
            try:
                return self.get_password("openai_api_key")
            except Exception:
                return self.openai_api_key

        return None

    def resolve_model(self) -> str:
        provider = self.normalise_provider(self.api_provider)
        model = (self.openai_model or "").strip()
        if provider == "Gemini":
            if not model or model.startswith("gpt-"):
                return DEFAULT_GEMINI_MODEL
            return model

        if not model or model in {"gpt-5", "gpt-5-mini"} or model.startswith("gemini-"):
            return DEFAULT_OPENAI_MODEL
        return model

    def resolve_service_user(self) -> str:
        return self.service_user or "Administrator"

    @staticmethod
    def get_settings() -> "AISettings":
        settings = frappe.get_single("AI Settings")
        settings.api_provider = settings.normalise_provider(settings.api_provider)
        settings.openai_model = settings.resolve_model()
        resolved_key = settings.resolve_api_key()
        if not resolved_key:
            frappe.throw(f"Configure a {settings.api_provider} API key in AI Settings to use the assistant.")

        settings._resolved_api_key = resolved_key  # type: ignore[attr-defined]
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
