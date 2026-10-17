"""OpenAI-compatible chat client that returns validated JSON.

Works with a local DGX served through vLLM, SGLang, or Ollama, or with any hosted provider.
"""

import json
import re
import threading
import time

import httpx
from openai import APIConnectionError, APITimeoutError, OpenAI

from neura1.config import settings


class LLMUnavailable(RuntimeError):
    pass


def client() -> OpenAI:
    """The main endpoint, always (used by tools that must say exactly which model they ran)."""
    if not settings.llm_base_url or not settings.llm_model:
        raise LLMUnavailable("No model endpoint configured (NEURA1_LLM_BASE_URL / NEURA1_LLM_MODEL)")
    return OpenAI(base_url=settings.llm_base_url, api_key=settings.llm_api_key, timeout=settings.llm_timeout,
                  max_retries=0)


# ---------- main endpoint with an automatic fallback ----------

_state = {"checked": 0.0, "up": True}
_lock = threading.Lock()
last_model: str | None = None  # the model that produced the most recent chat_json result


def _primary_up() -> bool:
    """Is the main endpoint reachable? Checked at most every 30 s, so a DGX that drops off the network costs one
    short probe, not a long timeout on every request."""
    if not settings.llm_fallback_base_url:
        return True
    with _lock:
        if time.monotonic() - _state["checked"] < 30:
            return _state["up"]
        try:
            r = httpx.get(f"{settings.llm_base_url.rstrip('/')}/models", timeout=3,
                          headers={"Authorization": f"Bearer {settings.llm_api_key}"})
            _state["up"] = r.status_code < 500
        except httpx.HTTPError:
            _state["up"] = False
        _state["checked"] = time.monotonic()
        return _state["up"]


def _mark_down() -> None:
    with _lock:
        _state.update(up=False, checked=time.monotonic())


def active() -> tuple[OpenAI, str]:
    """The client and model to use now: the main endpoint when it is reachable, otherwise the fallback."""
    if _primary_up() or not settings.llm_fallback_base_url:
        return client(), settings.llm_model
    return (OpenAI(base_url=settings.llm_fallback_base_url, api_key=settings.llm_fallback_api_key,
                   timeout=settings.llm_timeout, max_retries=0), settings.llm_fallback_model or settings.llm_model)


def complete(**kwargs):
    """chat.completions.create on the active endpoint; if the main one fails to connect, retry once on the fallback."""
    global last_model
    c, model = active()
    try:
        r = c.chat.completions.create(model=model, **kwargs)
    except (APIConnectionError, APITimeoutError):
        if not settings.llm_fallback_base_url or model == settings.llm_fallback_model:
            raise
        _mark_down()
        c, model = active()
        r = c.chat.completions.create(model=model, **kwargs)
    last_model = model
    return r


def status() -> dict:
    up = _primary_up()
    return {"model": settings.llm_model if up else (settings.llm_fallback_model or settings.llm_model),
            "primary": settings.llm_model, "on_fallback": not up}


def _parse_json(text: str) -> dict:
    text = re.sub(r"^.*?</think>", "", text, flags=re.S)  # reasoning models may emit a think block
    match = re.search(r"\{.*\}", text, flags=re.S)
    if not match:
        raise ValueError(f"Model did not return JSON: {text[:200]}")
    return json.loads(match.group(0))


def chat_json(system: str, user: str, schema: dict, name: str) -> dict:
    """Ask for JSON matching `schema`. Uses structured output where the server supports it."""
    messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
    try:
        resp = complete(messages=messages, temperature=0,
                        response_format={"type": "json_schema", "json_schema": {"name": name, "schema": schema}})
    except (APIConnectionError, APITimeoutError):
        raise
    except Exception:
        resp = complete(temperature=0, messages=messages + [{"role": "user", "content": "Return only JSON matching this schema:\n"
                                                                       + json.dumps(schema)}])
    return _parse_json(resp.choices[0].message.content or "")


def embed(texts: list[str]) -> list[list[float]]:
    """Embeddings from the same OpenAI-compatible endpoint (Ollama, vLLM). Raises LLMUnavailable if not configured."""
    if not settings.llm_embed_model:
        raise LLMUnavailable("No embedding model configured (NEURA1_LLM_EMBED_MODEL)")
    c = OpenAI(base_url=settings.llm_embed_base_url, api_key=settings.llm_embed_api_key or "not-needed",
               timeout=settings.llm_timeout, max_retries=0) if settings.llm_embed_base_url else client()
    resp = c.embeddings.create(model=settings.llm_embed_model, input=texts)
    return [d.embedding for d in resp.data]
