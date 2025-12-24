from __future__ import annotations

from typing import Any, List, Optional

import requests


def _extract_text(payload: Any) -> List[str]:
    if payload is None:
        return []

    if isinstance(payload, str):
        stripped = payload.strip()
        return [stripped] if stripped else []

    if isinstance(payload, dict):
        segments: List[str] = []
        for key in ("text", "output", "content"):
            value = payload.get(key)
            if isinstance(value, str):
                stripped = value.strip()
                if stripped:
                    segments.append(stripped)
            elif isinstance(value, (list, dict)):
                segments.extend(_extract_text(value))
        for value in payload.values():
            if isinstance(value, (list, dict)):
                segments.extend(_extract_text(value))
        return segments

    if isinstance(payload, list):
        segments: List[str] = []
        for item in payload:
            segments.extend(_extract_text(item))
        return segments

    return []


def _coerce_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return str(value)


def _messages_to_gemini_payload(messages: List[dict]) -> dict:
    system_segments: List[str] = []
    contents: List[dict] = []

    for message in messages:
        role = (message.get("role") or "").strip().lower()
        content = _coerce_text(message.get("content"))
        if not content.strip():
            continue

        if role == "system":
            system_segments.append(content)
            continue

        gemini_role = "user"
        if role == "assistant":
            gemini_role = "model"

        contents.append({"role": gemini_role, "parts": [{"text": content}]})

    payload: dict = {"contents": contents}
    if system_segments:
        payload["systemInstruction"] = {"parts": [{"text": "\n\n".join(system_segments)}]}

    return payload


def generate_completion(
    *,
    api_key: str,
    model: str,
    system_prompt: Optional[str] = None,
    user_prompt: Optional[str] = None,
    messages: Optional[List[dict]] = None,
    temperature: Optional[float] = 0.1,
    max_completion_tokens: int = 900,
    timeout: int = 60,
) -> str:
    if messages is None:
        if system_prompt is None or user_prompt is None:
            raise ValueError("Either messages or both system_prompt and user_prompt must be provided.")
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

    payload = _messages_to_gemini_payload(messages)
    generation_config: dict[str, Any] = {"maxOutputTokens": max_completion_tokens}
    if temperature is not None:
        generation_config["temperature"] = temperature
    payload["generationConfig"] = generation_config

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    response = requests.post(url, params={"key": api_key}, json=payload, timeout=timeout)

    try:
        response.raise_for_status()
    except requests.HTTPError as err:
        details = None
        try:
            details = response.json()
        except Exception:
            details = response.text
        raise RuntimeError(f"Gemini request failed: {details}") from err

    data = response.json()
    candidates = data.get("candidates") or []
    if not candidates:
        feedback = data.get("promptFeedback") or {}
        if feedback:
            raise RuntimeError(f"Gemini returned no candidates: {feedback}")
        return ""

    candidate = candidates[0] or {}
    content = candidate.get("content") or {}
    parts = content.get("parts") or []
    segments: List[str] = []
    for part in parts:
        if isinstance(part, dict) and isinstance(part.get("text"), str):
            stripped = part["text"].strip()
            if stripped:
                segments.append(stripped)
        else:
            segments.extend(_extract_text(part))

    return "\n\n".join(seg for seg in segments if seg) or ""
