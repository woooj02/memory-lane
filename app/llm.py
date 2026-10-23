"""One call shape for the AI step: Together AI, the Claude API, or Amazon Bedrock.

`structured(system, prompt, schema)` returns a dict that matches `schema`.
All three engines constrain the answer to the JSON schema. Together's models
are open models, so the answer is also checked here and retried once if it
isn't valid JSON.
"""

from __future__ import annotations

import json
import re
import time

from . import config


class LLMError(RuntimeError):
    pass


def engine() -> str:
    return config.llm_provider()


def model(fast: bool = False) -> str:
    e = engine()
    if e == "manual":
        return "read by hand (./run.sh manual)"
    if e == "together":
        return config.TOGETHER_FAST_MODEL if fast else config.TOGETHER_MODEL
    return config.BEDROCK_MODEL if e == "bedrock" else config.CLAUDE_MODEL


def structured(system: str, prompt: str, schema: dict, max_tokens: int = 16000, effort: str | None = None) -> dict:
    """effort="low" means speed matters more than polish (the live feed):
    on Together that picks the fast model."""
    provider = engine()
    if provider in ("mock", "manual"):
        raise LLMError(f"{provider} engine has no model")
    if provider == "together":
        fast = effort == "low"
        return together(model(fast), system, prompt, schema, max_tokens, fast=fast)[0]
    return _claude(provider, system, prompt, schema, max_tokens, effort)


# ---- Together AI (OpenAI-compatible chat completions) ----

TOGETHER_URL = "https://api.together.xyz/v1/chat/completions"
_THINK = re.compile(r"<think>.*?</think>", re.S)
_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$")


def _parse(text: str) -> dict:
    text = _FENCE.sub("", _THINK.sub("", text or "").strip()).strip()
    data = json.loads(text)
    if not isinstance(data, dict):
        raise json.JSONDecodeError("not an object", text, 0)
    return data


def together(model_id: str, system: str, prompt: str, schema: dict, max_tokens: int = 16000,
             fast: bool = False) -> tuple[dict, dict]:
    """(answer, usage). Retries once on a bad answer, a rate limit or a server error."""
    import httpx

    key = config.TOGETHER_API_KEY
    if not key:
        raise LLMError("TOGETHER_API_KEY is not set")
    body = {
        "model": model_id,
        "max_tokens": max_tokens,
        "temperature": 0.2,
        "messages": [
            # Together's docs: say "JSON only" and show the schema in the prompt too,
            # not just in response_format.
            {"role": "system", "content": f"{system}\n\nAnswer only with one JSON object that matches this "
                                          f"JSON Schema, with no other text:\n{json.dumps(schema, ensure_ascii=False)}"},
            {"role": "user", "content": prompt},
        ],
        "response_format": {"type": "json_schema", "json_schema": {"name": "answer", "schema": schema}},
    }
    if fast:
        body["reasoning"] = {"enabled": False}  # live lines: no thinking, just the translation

    last = "no answer"
    for attempt in range(3):
        try:
            r = httpx.post(TOGETHER_URL, json=body, timeout=600,
                           headers={"Authorization": f"Bearer {key}"})
        except httpx.HTTPError as exc:
            last = f"network error: {exc}"
            time.sleep(2 * (attempt + 1))
            continue
        if r.status_code == 400 and "reasoning" in body and "reason" in r.text.lower():
            body.pop("reasoning")  # this model doesn't take the switch; ask again without it
            continue
        if r.status_code in (429, 500, 502, 503, 504):
            last = f"Together HTTP {r.status_code}"
            time.sleep(2 * (attempt + 1))
            continue
        if r.status_code >= 400:
            raise LLMError(f"Together HTTP {r.status_code}: {r.text[:300]}")
        out = r.json()
        choice = (out.get("choices") or [{}])[0]
        if choice.get("finish_reason") == "length":
            raise LLMError("the answer was cut off (max_tokens)")
        try:
            return _parse((choice.get("message") or {}).get("content", "")), out.get("usage") or {}
        except json.JSONDecodeError:
            last = "the model did not return JSON"
    raise LLMError(last)


# ---- Claude: the Claude API or Amazon Bedrock ----

def _claude(provider: str, system: str, prompt: str, schema: dict, max_tokens: int, effort: str | None) -> dict:
    output_config = {"effort": effort or config.CLAUDE_EFFORT, "format": {"type": "json_schema", "schema": schema}}
    system_blocks = [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}]
    messages = [{"role": "user", "content": prompt}]

    if provider == "bedrock":
        from anthropic import AnthropicBedrockMantle

        client = AnthropicBedrockMantle(aws_region=config.AWS_REGION)
        # Server-side fallbacks are not offered on Bedrock; a refusal is reported below.
        response = client.messages.create(model=config.BEDROCK_MODEL, max_tokens=max_tokens,
                                          system=system_blocks, messages=messages,
                                          output_config=output_config)
    else:
        import anthropic

        client = anthropic.Anthropic()
        # The beta endpoint is used only for the server-side refusal fallback:
        # if a safety classifier declines a benign transcript, the API retries
        # it on another model inside the same call.
        response = client.beta.messages.create(model=config.CLAUDE_MODEL, max_tokens=max_tokens,
                                               system=system_blocks, messages=messages,
                                               output_config=output_config,
                                               betas=["server-side-fallback-2026-07-01"],
                                               fallbacks="default")

    if response.stop_reason == "refusal":
        raise LLMError("the model declined this transcript")
    if response.stop_reason == "max_tokens":
        raise LLMError("the answer was cut off (max_tokens)")
    text = next((b.text for b in response.content if b.type == "text"), "")
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise LLMError("the model did not return JSON") from exc
