from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass

from .config import CitiesAIConfig


@dataclass(frozen=True)
class LLMSettings:
    base_url: str
    model: str
    api_key: str
    api_key_env: str


def resolve_llm_settings(cfg: CitiesAIConfig) -> LLMSettings | None:
    api_key_env = os.environ.get("CITIESAI_LLM_API_KEY_ENV", "").strip() or cfg.llm_api_key_env
    api_key = os.environ.get(api_key_env, "").strip()
    if not api_key:
        return None

    base_url = os.environ.get("CITIESAI_LLM_BASE_URL", "").strip() or cfg.llm_base_url
    model = os.environ.get("CITIESAI_LLM_MODEL", "").strip() or cfg.llm_model
    return LLMSettings(base_url=base_url.rstrip("/"), model=model, api_key=api_key, api_key_env=api_key_env)


def build_system_prompt() -> str:
    return (
        "You are CitiesAI, a read-only gameplay advisor for Cities: Skylines II. "
        "Ground every answer in the provided city snapshot metrics first, then wiki and "
        "encyclopedia evidence. Do not invent metrics. If data is stale, partial, or "
        "unavailable, say so. Give practical next steps. End with a short Sources line "
        "listing wiki URLs and encyclopedia entry titles used."
    )


def generate_answer(prompt: str, *, cfg: CitiesAIConfig) -> str:
    settings = resolve_llm_settings(cfg)
    if settings is None:
        raise RuntimeError(
            "No LLM API key found. Set MISTRAL_API_KEY (free tier at console.mistral.ai) "
            "or use --no-llm for prompt-bundle output."
        )

    url = f"{settings.base_url}/chat/completions"
    payload = {
        "model": settings.model,
        "messages": [
            {"role": "system", "content": build_system_prompt()},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.3,
    }
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {settings.api_key}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"LLM request failed ({exc.code}): {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"LLM request failed: {exc.reason}") from exc

    choices = data.get("choices") or []
    if not choices:
        raise RuntimeError("LLM returned no choices.")
    message = choices[0].get("message") or {}
    content = message.get("content")
    if not content:
        raise RuntimeError("LLM returned empty content.")
    return str(content).strip()
