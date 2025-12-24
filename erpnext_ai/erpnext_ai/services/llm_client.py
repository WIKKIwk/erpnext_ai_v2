from __future__ import annotations

from typing import List, Optional

from .gemini_client import generate_completion as generate_gemini_completion
from .openai_client import generate_completion as generate_openai_completion


def _normalise_provider(provider: str | None) -> str:
    provider_value = (provider or "OpenAI").strip()
    lower = provider_value.lower()
    if lower == "gemini":
        return "Gemini"
    if lower == "openai":
        return "OpenAI"
    return provider_value or "OpenAI"


def generate_completion(
    *,
    provider: str,
    api_key: str,
    model: str,
    system_prompt: Optional[str] = None,
    user_prompt: Optional[str] = None,
    messages: Optional[List[dict]] = None,
    temperature: Optional[float] = 0.1,
    max_completion_tokens: int = 900,
    timeout: int = 60,
) -> str:
    provider_value = _normalise_provider(provider)
    if provider_value == "Gemini":
        return generate_gemini_completion(
            api_key=api_key,
            model=model,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            messages=messages,
            temperature=temperature,
            max_completion_tokens=max_completion_tokens,
            timeout=timeout,
        )
    return generate_openai_completion(
        api_key=api_key,
        model=model,
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        messages=messages,
        temperature=temperature,
        max_completion_tokens=max_completion_tokens,
        timeout=timeout,
    )
