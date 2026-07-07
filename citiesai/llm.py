from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from typing import Any

from .agent_tools import TOOL_DEFINITIONS, execute_tool
from .config import DEFAULT_MAX_TOOL_ROUNDS, CitiesAIConfig


@dataclass(frozen=True)
class LLMSettings:
    base_url: str
    model: str
    api_key: str
    api_key_env: str


@dataclass(frozen=True)
class AgenticResult:
    answer: str
    sources: list[dict[str, Any]]
    tool_calls: list[str]
    fallback_used: bool = False


LLM_PRESETS: dict[str, dict[str, str]] = {
    "mistral": {
        "label": "Mistral Cloud",
        "base_url": "https://api.mistral.ai/v1",
        "model": "mistral-medium-latest",
        "api_key_env": "MISTRAL_API_KEY",
    },
    "openai": {
        "label": "OpenAI",
        "base_url": "https://api.openai.com/v1",
        "model": "gpt-5.5",
        "api_key_env": "OPENAI_API_KEY",
    },
    "local": {
        "label": "Local (Ollama / LM Studio)",
        "base_url": "http://127.0.0.1:11434/v1",
        "model": "llama3.2",
        "api_key_env": "CITIESAI_LOCAL_API_KEY",
    },
}


TOOL_STATUS_MESSAGES: dict[str, str] = {
    "get_metric_group": "Reading city metrics…",
    "search_wiki": "Searching Cities Wiki…",
    "search_encyclopedia": "Searching in-game encyclopedia…",
    "get_city_history": "Loading city history…",
    "get_transit_lines": "Analyzing transit lines…",
    "get_access_gaps": "Checking transit access gaps…",
    "get_demand_factors": "Reading RCI demand drivers…",
    "get_utilities_services": "Checking utilities and services…",
}

AGENTIC_LOOP_ERROR = (
    "Agentic loop exceeded maximum tool rounds. "
    "Try disabling Deep research in Settings or ask a narrower question."
)


def resolve_llm_settings(cfg: CitiesAIConfig) -> LLMSettings | None:
    api_key_env = os.environ.get("CITIESAI_LLM_API_KEY_ENV", "").strip() or cfg.llm_api_key_env
    api_key = os.environ.get(api_key_env, "").strip()
    if not api_key and cfg.llm_provider == "local":
        api_key = "local"
    if not api_key:
        return None

    base_url = os.environ.get("CITIESAI_LLM_BASE_URL", "").strip() or cfg.llm_base_url
    model = os.environ.get("CITIESAI_LLM_MODEL", "").strip() or cfg.llm_model
    return LLMSettings(base_url=base_url.rstrip("/"), model=model, api_key=api_key, api_key_env=api_key_env)


def max_tool_rounds(cfg: CitiesAIConfig) -> int:
    env = os.environ.get("CITIESAI_LLM_MAX_TOOL_ROUNDS", "").strip()
    if env:
        try:
            return max(1, int(env))
        except ValueError:
            pass
    return max(1, cfg.llm_max_tool_rounds or DEFAULT_MAX_TOOL_ROUNDS)


def build_system_prompt(*, agentic: bool = False, force_answer: bool = False) -> str:
    base = (
        "You are CitiesAI, a read-only gameplay advisor for Cities: Skylines II. "
        "Use the city snapshot metrics first, then wiki and encyclopedia evidence. "
        "Never invent metrics.\n\n"
        "Output format:\n"
        "- Open with a plain paragraph (no numbering): 1-2 sentences diagnosing the "
        "problem using the city's actual numbers.\n"
        "- Then one numbered list of 3-5 concrete in-game actions (what to build, "
        "budget sliders, policies, zoning). Most impactful first. Use only this single "
        "list — do not number the diagnosis or add a second outline.\n\n"
        "Rules:\n"
        "- No preamble, no restating the question, no generic filler.\n"
        "- No headers unless the answer genuinely needs them.\n"
        "- Stay under ~150 words unless the user asks for depth.\n"
        "- Do not mention snapshot age, freshness, or staleness."
    )
    if agentic:
        base += (
            "\n\nYou have tools to fetch metric groups, search wiki/encyclopedia, "
            "history, and transit lines. Use the city brief and any pre-retrieved "
            "sources first. Call tools only for missing specifics (one metric group, "
            "transit detail, etc.). Answer after at most 2 tool rounds unless the user "
            "explicitly asks for exhaustive research."
        )
        if force_answer:
            base += "\n\nYou have used all research steps. Answer now from the conversation context."
    else:
        base += "\n- No Sources section, URLs, or citations in the answer body."
    return base


def _supports_temperature(settings: LLMSettings) -> bool:
    if "api.openai.com" not in settings.base_url:
        return True
    model = settings.model.lower()
    return not any(model.startswith(prefix) for prefix in ("gpt-5", "o1", "o3", "o4"))


def _chat_payload(
    messages: list[dict[str, Any]],
    settings: LLMSettings,
    *,
    stream: bool,
    tools: list[dict[str, Any]] | None = None,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "model": settings.model,
        "messages": messages,
    }
    if _supports_temperature(settings):
        payload["temperature"] = 0.3
    if stream:
        payload["stream"] = True
    if tools:
        payload["tools"] = tools
        payload["tool_choice"] = "auto"
    return payload


def _post_chat(payload: dict[str, object], settings: LLMSettings, *, stream: bool) -> Any:
    url = f"{settings.base_url}/chat/completions"
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
        return urllib.request.urlopen(request, timeout=120)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"LLM request failed ({exc.code}): {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"LLM request failed: {exc.reason}") from exc


def _parse_message(data: dict[str, Any]) -> dict[str, Any]:
    choices = data.get("choices") or []
    if not choices:
        raise RuntimeError("LLM returned no choices.")
    return choices[0].get("message") or {}


def _stream_chat_tokens(
    messages: list[dict[str, Any]],
    settings: LLMSettings,
    *,
    tools: list[dict[str, Any]] | None = None,
) -> Iterator[str]:
    payload = _chat_payload(messages, settings, stream=True, tools=tools)
    with _post_chat(payload, settings, stream=True) as response:
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


def _complete_chat(
    messages: list[dict[str, Any]],
    settings: LLMSettings,
    *,
    tools: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    payload = _chat_payload(messages, settings, stream=False, tools=tools)
    with _post_chat(payload, settings, stream=False) as response:
        data = json.loads(response.read().decode("utf-8"))
    return _parse_message(data)


def _force_final_answer(messages: list[dict[str, Any]], settings: LLMSettings) -> str:
    final_messages = list(messages)
    final_messages[0] = {
        "role": "system",
        "content": build_system_prompt(agentic=True, force_answer=True),
    }
    message = _complete_chat(final_messages, settings)
    content = message.get("content")
    if not content:
        raise RuntimeError("LLM returned empty content.")
    return str(content).strip()


def iter_agentic_answer(
    question: str,
    *,
    city_brief: str,
    snapshot: dict[str, Any],
    cfg: CitiesAIConfig,
    history_messages: list[dict[str, str]] | None = None,
    retrieval_context: str | None = None,
    retrieval_bundle: str | None = None,
    user_content: str | None = None,
) -> Iterator[tuple[str, Any]]:
    settings = resolve_llm_settings(cfg)
    if settings is None:
        raise RuntimeError(
            "No LLM API key found. Add your Mistral key in Settings or set MISTRAL_API_KEY."
        )

    if user_content is None:
        parts = [f"# City brief\n{city_brief}"]
        if retrieval_context:
            parts.append(f"## Pre-retrieved sources\n{retrieval_context}")
        parts.append(f"## Question\n{question}")
        user_content = "\n\n".join(parts)

    messages: list[dict[str, Any]] = [
        {"role": "system", "content": build_system_prompt(agentic=True)},
        {"role": "user", "content": user_content},
    ]
    if history_messages:
        messages = [messages[0], *history_messages[-8:], messages[1]]

    yield ("status", "Thinking…")

    sources: list[dict[str, Any]] = []
    tool_names: list[str] = []
    rounds = max_tool_rounds(cfg)

    for _ in range(rounds):
        message = _complete_chat(messages, settings, tools=TOOL_DEFINITIONS)
        tool_calls = message.get("tool_calls") or []
        if not tool_calls:
            content = message.get("content")
            if not content:
                raise RuntimeError("LLM returned empty content.")
            answer = str(content).strip()
            for token in stream_text_chunks(answer):
                yield ("token", token)
            yield (
                "result",
                AgenticResult(answer=answer, sources=sources, tool_calls=tool_names),
            )
            return

        messages.append(message)
        for call in tool_calls:
            fn = call.get("function") or {}
            name = str(fn.get("name", ""))
            raw_args = fn.get("arguments") or "{}"
            try:
                args = json.loads(raw_args) if isinstance(raw_args, str) else raw_args
            except json.JSONDecodeError:
                args = {}
            if not isinstance(args, dict):
                args = {}
            tool_names.append(name)
            yield ("status", TOOL_STATUS_MESSAGES.get(name, f"Running {name}…"))
            if name in ("search_wiki", "search_encyclopedia"):
                sources.append({"tool": name, "query": args.get("query", "")})
            result = execute_tool(name, args, snapshot=snapshot)
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": call.get("id", name),
                    "content": result,
                }
            )

    yield ("status", "Wrapping up answer…")
    try:
        answer = _force_final_answer(messages, settings)
        yield (
            "result",
            AgenticResult(
                answer=answer,
                sources=sources,
                tool_calls=tool_names,
                fallback_used=True,
            ),
        )
        return
    except RuntimeError:
        pass

    if retrieval_bundle:
        answer = generate_answer(retrieval_bundle, cfg=cfg)
        yield (
            "result",
            AgenticResult(
                answer=answer,
                sources=sources,
                tool_calls=tool_names,
                fallback_used=True,
            ),
        )
        return

    raise RuntimeError(AGENTIC_LOOP_ERROR)


def generate_agentic_answer(
    question: str,
    *,
    city_brief: str,
    snapshot: dict[str, Any],
    cfg: CitiesAIConfig,
    history_messages: list[dict[str, str]] | None = None,
    retrieval_context: str | None = None,
    retrieval_bundle: str | None = None,
    user_content: str | None = None,
    on_status: Callable[[str], None] | None = None,
) -> AgenticResult:
    result: AgenticResult | None = None
    for kind, payload in iter_agentic_answer(
        question,
        city_brief=city_brief,
        snapshot=snapshot,
        cfg=cfg,
        history_messages=history_messages,
        retrieval_context=retrieval_context,
        retrieval_bundle=retrieval_bundle,
        user_content=user_content,
    ):
        if kind == "status" and on_status:
            on_status(str(payload))
        elif kind == "result":
            result = payload
    if result is None:
        raise RuntimeError("Agentic loop produced no answer.")
    return result


def generate_answer(
    prompt: str,
    *,
    cfg: CitiesAIConfig,
    history_messages: list[dict[str, str]] | None = None,
) -> str:
    settings = resolve_llm_settings(cfg)
    if settings is None:
        raise RuntimeError(
            "No LLM API key found. Add your Mistral key in Settings or set MISTRAL_API_KEY."
        )

    messages: list[dict[str, Any]] = [
        {"role": "system", "content": build_system_prompt()},
        {"role": "user", "content": prompt},
    ]
    if history_messages:
        messages = [messages[0], *history_messages[-8:], messages[1]]
    message = _complete_chat(messages, settings)
    content = message.get("content")
    if not content:
        raise RuntimeError("LLM returned empty content.")
    return str(content).strip()


def stream_answer(
    prompt: str,
    *,
    cfg: CitiesAIConfig,
    history_messages: list[dict[str, str]] | None = None,
) -> Iterator[str]:
    settings = resolve_llm_settings(cfg)
    if settings is None:
        raise RuntimeError(
            "No LLM API key found. Add your Mistral key in Settings or set MISTRAL_API_KEY."
        )

    messages: list[dict[str, Any]] = [
        {"role": "system", "content": build_system_prompt()},
        {"role": "user", "content": prompt},
    ]
    if history_messages:
        messages = [messages[0], *history_messages[-8:], messages[1]]
    yield from _stream_chat_tokens(messages, settings)


def stream_text_chunks(text: str, *, chunk_size: int = 12) -> Iterator[str]:
    for index in range(0, len(text), chunk_size):
        yield text[index : index + chunk_size]


def test_api_key(*, cfg: CitiesAIConfig) -> dict[str, str | bool]:
    settings = resolve_llm_settings(cfg)
    if settings is None:
        return {"ok": False, "error": "No API key configured."}
    try:
        messages = [
            {"role": "system", "content": "Reply briefly."},
            {"role": "user", "content": "Reply with exactly: OK"},
        ]
        message = _complete_chat(messages, settings)
        content = message.get("content", "")
        return {"ok": True, "model": settings.model, "sample": str(content).strip()[:80]}
    except RuntimeError as exc:
        return {"ok": False, "error": str(exc)}
