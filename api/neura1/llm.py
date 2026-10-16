"""OpenAI-compatible chat client that returns validated JSON.

Works with a local DGX served through vLLM, SGLang, or Ollama, or with any hosted provider.
"""

import json
import re

from openai import OpenAI

from neura1.config import settings


class LLMUnavailable(RuntimeError):
    pass


def client() -> OpenAI:
    if not settings.llm_base_url or not settings.llm_model:
        raise LLMUnavailable("No model endpoint configured (NEURA1_LLM_BASE_URL / NEURA1_LLM_MODEL)")
    return OpenAI(base_url=settings.llm_base_url, api_key=settings.llm_api_key, timeout=settings.llm_timeout,
                  max_retries=0)


def _parse_json(text: str) -> dict:
    text = re.sub(r"^.*?</think>", "", text, flags=re.S)  # reasoning models may emit a think block
    match = re.search(r"\{.*\}", text, flags=re.S)
    if not match:
        raise ValueError(f"Model did not return JSON: {text[:200]}")
    return json.loads(match.group(0))


def chat_json(system: str, user: str, schema: dict, name: str) -> dict:
    """Ask for JSON matching `schema`. Uses structured output where the server supports it."""
    c = client()
    messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
    try:
        resp = c.chat.completions.create(
            model=settings.llm_model, messages=messages, temperature=0,
            response_format={"type": "json_schema", "json_schema": {"name": name, "schema": schema}},
        )
    except Exception:
        resp = c.chat.completions.create(
            model=settings.llm_model, temperature=0,
            messages=messages + [{"role": "user", "content": "Return only JSON matching this schema:\n"
                                  + json.dumps(schema)}],
        )
    return _parse_json(resp.choices[0].message.content or "")


def embed(texts: list[str]) -> list[list[float]]:
    """Embeddings from the same OpenAI-compatible endpoint (Ollama, vLLM). Raises LLMUnavailable if not configured."""
    if not settings.llm_embed_model:
        raise LLMUnavailable("No embedding model configured (NEURA1_LLM_EMBED_MODEL)")
    resp = client().embeddings.create(model=settings.llm_embed_model, input=texts)
    return [d.embedding for d in resp.data]
