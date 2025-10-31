from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

import requests
from requests import Response

from .config import BotConfig, OrderSettings, ReportSettings


class ERPNextError(Exception):
    """Raised when ERPNext returns an error response."""


class ERPNextClient:
    """Helper for invoking ERPNext HTTP APIs with token authentication."""

    def __init__(self, config: BotConfig):
        self.base_url = config.frappe_base_url.rstrip("/")
        self.timeout = config.request_timeout
        self.verify_endpoint = config.verification_endpoint

    def _headers(self, api_key: str, api_secret: str) -> Dict[str, str]:
        return {
            "Authorization": f"token {api_key}:{api_secret}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def _handle_response(self, response: Response) -> Dict[str, object]:
        if response.status_code >= 400:
            try:
                payload = response.json()
                message = payload.get("message") or payload.get("exc") or response.text
            except ValueError:
                message = response.text
            raise ERPNextError(f"ERPNext responded with {response.status_code}: {message}")
        try:
            return response.json()
        except ValueError as exc:  # noqa: B904
            raise ERPNextError("ERPNext returned an invalid JSON payload.") from exc

    def validate_credentials(self, api_key: str, api_secret: str) -> Tuple[bool, str]:
        url = f"{self.base_url}{self.verify_endpoint}"
        try:
            response = requests.get(url, headers=self._headers(api_key, api_secret), timeout=self.timeout)
        except requests.RequestException as exc:
            return False, f"Connection to ERPNext failed: {exc}"
        if response.status_code == 401:
            return False, "ERPNext rejected the API credentials (401 Unauthorized)."
        if response.status_code >= 400:
            return False, f"ERPNext returned {response.status_code}: {response.text}"
        try:
            data = response.json()
        except ValueError:
            return True, "Credentials valid, but ERPNext response could not be decoded."
        if isinstance(data, dict):
            user = data.get("message") or data.get("full_name") or ""
            return True, f"Credentials validated for {user}".strip()
        return True, "Credentials validated successfully."

    def fetch_report(
        self,
        *,
        api_key: str,
        api_secret: str,
        settings: ReportSettings,
    ) -> List[Dict[str, object]]:
        url = f"{self.base_url}/api/resource/{settings.resource}"
        params = {
            "limit_page_length": settings.limit,
            "order_by": settings.order_by,
        }
        if settings.fields:
            params["fields"] = json.dumps(settings.fields)
        try:
            response = requests.get(
                url,
                headers=self._headers(api_key, api_secret),
                params=params,
                timeout=self.timeout,
            )
        except requests.RequestException as exc:
            raise ERPNextError(f"Failed to reach ERPNext for report data: {exc}") from exc
        payload = self._handle_response(response)
        if isinstance(payload, dict) and "data" in payload:
            data = payload["data"]
            if isinstance(data, list):
                return data  # type: ignore[return-value]
        raise ERPNextError("Unexpected ERPNext response structure while fetching report data.")

    def create_lead(
        self,
        *,
        api_key: str,
        api_secret: str,
        order_settings: OrderSettings,
        lead_name: str,
        phone: Optional[str],
        notes: str,
    ) -> Dict[str, object]:
        url = f"{self.base_url}/api/resource/{order_settings.target_doctype}"
        payload: Dict[str, object] = {
            "doctype": order_settings.target_doctype,
            "lead_name": lead_name,
            "status": order_settings.status,
            "source": order_settings.lead_source,
            "notes": notes,
        }
        if phone:
            payload["mobile_no"] = phone
            payload["phone"] = phone
        if order_settings.territory:
            payload["territory"] = order_settings.territory

        try:
            response = requests.post(
                url,
                headers=self._headers(api_key, api_secret),
                data=json.dumps(payload),
                timeout=self.timeout,
            )
        except requests.RequestException as exc:
            raise ERPNextError(f"Failed to create lead in ERPNext: {exc}") from exc
        return self._handle_response(response)

    def upload_file(
        self,
        *,
        api_key: str,
        api_secret: str,
        file_name: str,
        file_path: Path,
        attach_to_doctype: Optional[str] = None,
        attach_to_name: Optional[str] = None,
    ) -> Dict[str, object]:
        url = f"{self.base_url}/api/method/upload_file"
        headers = self._headers(api_key, api_secret)
        # The upload endpoint expects multipart form; remove JSON content type.
        headers.pop("Content-Type", None)
        with file_path.open("rb") as file_handle:
            file_bytes = file_handle.read()
        files = {
            "file": (file_name, file_bytes, "application/octet-stream"),
        }
        data = {
            "is_private": "1",
        }
        if attach_to_doctype:
            data["doctype"] = attach_to_doctype
        if attach_to_name:
            data["docname"] = attach_to_name
        try:
            response = requests.post(
                url,
                headers=headers,
                files=files,
                data=data,
                timeout=self.timeout,
            )
        except requests.RequestException as exc:
            raise ERPNextError(f"Failed to upload file to ERPNext: {exc}") from exc
        return self._handle_response(response)
