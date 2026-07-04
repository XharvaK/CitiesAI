from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

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
        "Use the city snapshot metrics first, then wiki and encyclopedia evidence. "
        "Never invent metrics.\n\n"
        "Output format:\n"
        "1. Diagnose the problem in 1-2 sentences using the city's actual numbers.\n"
        "2. Give a short numbered list of concrete in-game actions (what to build, "
        "budget sliders, policies, zoning). Most impactful first.\n\n"
        "Rules:\n"
        "- No Sources section, URLs, or citations.\n"
        "- No preamble, no restating the question, no generic filler.\n"
        "- No headers unless the answer genuinely needs them.\n"
        "- Stay under ~150 words unless the user asks for depth.\n"
        "- Do not mention snapshot age, freshness, or staleness."
    )


def _chat_payload(prompt: str, settings: LLMSettings, *, stream: bool) -> dict[str, object]:
    payload: dict[str, object] = {
        "model": settings.model,
        "messages": [
            {"role": "system", "content": build_system_prompt()},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.3,
    }
    if stream:
        payload["stream"] = True
    return payload


def _open_chat_request(prompt: str, settings: LLMSettings, *, stream: bool) -> Any:
    url = f"{settings.base_url}/chat/completions"
    body = json.dumps(_chat_payload(prompt, settings, stream=stream)).encode("utf-8")
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
        return urllib.request.urlopen(request, timeout=120)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"LLM request failed ({exc.code}): {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"LLM request failed: {exc.reason}") from exc


def generate_answer(prompt: str, *, cfg: CitiesAIConfig) -> str:
    settings = resolve_llm_settings(cfg)
    if settings is None:
        raise RuntimeError(
            "No LLM API key found. Add your Mistral key in Settings or set MISTRAL_API_KEY."
        )

    with _open_chat_request(prompt, settings, stream=False) as response:
        data = json.loads(response.read().decode("utf-8"))

    choices = data.get("choices") or []
    if not choices:
        raise RuntimeError("LLM returned no choices.")
    message = choices[0].get("message") or {}
    content = message.get("content")
    if not content:
        raise RuntimeError("LLM returned empty content.")
    return str(content).strip()


def stream_answer(prompt: str, *, cfg: CitiesAIConfig) -> Iterator[str]:
    settings = resolve_llm_settings(cfg)
    if settings is None:
        raise RuntimeError(
            "No LLM API key found. Add your Mistral key in Settings or set MISTRAL_API_KEY."
        )

    with _open_chat_request(prompt, settings, stream=True) as response:
        for raw_line in response:
            line = raw_line.decode("utf-8", errors="replace").strip()
            if not line or not line.startswith("data:"):
                continue
            data_part = line[5:].strip()
            if data_part == "[DONE]":
                break
            try:
                chunk = json.loads(data_part)
            except json.JSONDecodeError:
                continue
            choices = chunk.get("choices") or []
            if not choices:
                continue
            delta = choices[0].get("delta") or {}
            content = delta.get("content")
            if content:
                yield str(content)


def test_api_key(*, cfg: CitiesAIConfig) -> dict[str, str | bool]:
    settings = resolve_llm_settings(cfg)
    if settings is None:
        return {"ok": False, "error": "No API key configured."}
    try:
        with _open_chat_request("Reply with exactly: OK", settings, stream=False) as response:
            data = json.loads(response.read().decode("utf-8"))
        content = ((data.get("choices") or [{}])[0].get("message") or {}).get("content", "")
        return {"ok": True, "model": settings.model, "sample": str(content).strip()[:80]}
    except RuntimeError as exc:
        return {"ok": False, "error": str(exc)}
