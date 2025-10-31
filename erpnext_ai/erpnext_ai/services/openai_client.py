from __future__ import annotations

from typing import Any, List, Optional

from openai import BadRequestError, OpenAI


def _extract_text(content: Any) -> List[str]:
    """Normalise OpenAI chat/response payloads into plain-text segments."""
    if content is None:
        return []

    if isinstance(content, str):
        stripped = content.strip()
        return [stripped] if stripped else []

    if hasattr(content, "model_dump"):
        content = content.model_dump()

    if isinstance(content, dict):
        segments: List[str] = []
        content_type = content.get("type")
        if content_type in {"text", "output_text"}:
            for key in ("text", "content", "value"):
                value = content.get(key)
                if isinstance(value, str):
                    stripped = value.strip()
                    if stripped:
                        segments.append(stripped)
        for key in ("text", "content", "value", "message"):
            value = content.get(key)
            if isinstance(value, (str, list, dict)):
                segments.extend(_extract_text(value))
        if not segments and "reason" in content:
            segments.extend(_extract_text(content.get("reason")))
        return segments

    if isinstance(content, list):
        segments: List[str] = []
        for item in content:
            segments.extend(_extract_text(item))
        return segments

    return []


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

    client = OpenAI(api_key=api_key, timeout=timeout)
    request: dict = {
        "model": model,
        "messages": messages,
        "max_completion_tokens": max_completion_tokens,
    }
    if temperature is not None:
        request["temperature"] = temperature

    try:
        response = client.chat.completions.create(**request)
    except BadRequestError as err:
        # Some newer models only allow the default temperature; retry without it.
        if "temperature" in str(err).lower():
            request.pop("temperature", None)
            response = client.chat.completions.create(**request)
        else:
            raise

    choice = response.choices[0]
    message = getattr(choice, "message", None)
    if not message:
        return ""

    segments = _extract_text(getattr(message, "content", None))
    if not segments and hasattr(message, "model_dump"):
        payload = message.model_dump()
        segments = _extract_text(payload.get("content"))
        if not segments and payload.get("refusal"):
            segments = _extract_text(payload["refusal"])
    if not segments and hasattr(message, "refusal"):
        segments = _extract_text(getattr(message, "refusal"))

    return "\n\n".join(seg for seg in segments if seg) or ""
