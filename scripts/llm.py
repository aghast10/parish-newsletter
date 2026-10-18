"""One LLM call that returns JSON matching a schema, via the Anthropic or OpenAI API.

Provider and model come from the `llm` section of config.yaml:

    llm:
      provider: anthropic        # anthropic | openai
      model: claude-opus-5-5
      effort: medium             # anthropic only: low | medium | high | xhigh | max
      base_url: ...              # openai only, optional: any OpenAI-compatible API

Keys: ANTHROPIC_API_KEY / OPENAI_API_KEY in .env (the SDKs read them from the
environment, which common.load_env fills). No tools are passed to the model.
"""

import json
import time
from dataclasses import dataclass

MAX_TOKENS = 16000


@dataclass
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_creation_tokens: int = 0
    duration_ms: int = 0


class LLMError(Exception):
    pass


def complete_json(cfg, system, user, schema, schema_name="result"):
    """Return (parsed JSON, Usage). Raises LLMError on refusal, truncation or bad JSON."""
    provider = cfg.get("provider", "anthropic")
    if provider == "anthropic":
        call = _anthropic
    elif provider == "openai":
        call = _openai
    else:
        raise LLMError(f"Unknown llm.provider {provider!r} (use anthropic or openai)")

    start = time.monotonic()
    text, usage = call(cfg, system, user, schema, schema_name)
    usage.duration_ms = int((time.monotonic() - start) * 1000)
    try:
        return json.loads(text), usage
    except json.JSONDecodeError as e:
        raise LLMError(f"Model did not return valid JSON ({e}): {text[:300]}")


def _anthropic(cfg, system, user, schema, schema_name):
    import anthropic

    client = anthropic.Anthropic()
    try:
        # fallbacks="default": if a safety classifier declines, the API retries
        # on a fallback model inside the same call instead of just stopping.
        response = client.beta.messages.create(
            model=cfg.get("model", "claude-opus-5-5"),
            max_tokens=MAX_TOKENS,
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
            system=system,
            messages=[{"role": "user", "content": user}],
            output_config={
                "effort": cfg.get("effort", "medium"),
                "format": {"type": "json_schema", "schema": schema},
            },
        )
    except anthropic.APIStatusError as e:
        raise LLMError(f"Anthropic API error {e.status_code}: {e.message}")
    except anthropic.APIConnectionError as e:
        raise LLMError(f"Could not reach the Anthropic API: {e}")

    if response.stop_reason == "refusal":
        raise LLMError(f"Model refused: {response.stop_details}")
    if response.stop_reason == "max_tokens":
        raise LLMError("Output cut off at max_tokens.")

    text = next((b.text for b in response.content if b.type == "text"), "")
    u = response.usage
    return text, Usage(
        input_tokens=u.input_tokens or 0,
        output_tokens=u.output_tokens or 0,
        cache_read_tokens=u.cache_read_input_tokens or 0,
        cache_creation_tokens=u.cache_creation_input_tokens or 0,
    )


def _openai(cfg, system, user, schema, schema_name):
    import openai

    if not cfg.get("model"):
        raise LLMError("Set llm.model in config.yaml for the openai provider.")
    client = openai.OpenAI(base_url=cfg.get("base_url") or None)
    try:
        response = client.chat.completions.create(
            model=cfg["model"],
            max_completion_tokens=MAX_TOKENS,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            response_format={
                "type": "json_schema",
                "json_schema": {"name": schema_name, "strict": True, "schema": schema},
            },
        )
    except openai.APIStatusError as e:
        raise LLMError(f"OpenAI API error {e.status_code}: {e.message}")
    except openai.APIConnectionError as e:
        raise LLMError(f"Could not reach the OpenAI API: {e}")

    choice = response.choices[0]
    if getattr(choice.message, "refusal", None):
        raise LLMError(f"Model refused: {choice.message.refusal}")
    if choice.finish_reason == "length":
        raise LLMError("Output cut off at max_completion_tokens.")

    u = response.usage
    cached = getattr(getattr(u, "prompt_tokens_details", None), "cached_tokens", 0) or 0
    return choice.message.content or "", Usage(
        input_tokens=(u.prompt_tokens or 0) - cached,
        output_tokens=u.completion_tokens or 0,
        cache_read_tokens=cached,
    )
