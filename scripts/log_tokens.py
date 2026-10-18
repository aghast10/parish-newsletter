"""Log token usage of an LLM call to data/token_log.jsonl."""

import json
from datetime import datetime

from common import PROJECT_DIR

TOKEN_LOG = PROJECT_DIR / "data" / "token_log.jsonl"

# USD per million tokens. Models not listed are logged without a cost.
PRICING = {
    "claude-opus-5-5":   {"input": 4.00, "output": 20.00, "cache_read": 0.20, "cache_creation": 5.00},
    "claude-sonnet-5-5": {"input": 2.00, "output": 10.00, "cache_read": 0.20, "cache_creation": 2.50},
    "claude-haiku-5-5":  {"input": 0.10, "output": 0.50,  "cache_read": 0.01, "cache_creation": 0.125},
}


def log_usage(usage, month, step, provider, model):
    """Append one entry for an llm.Usage and return a summary line."""
    prices = PRICING.get(model)
    cost_usd = None
    if prices:
        cost_usd = (
            usage.input_tokens * prices["input"]
            + usage.output_tokens * prices["output"]
            + usage.cache_read_tokens * prices["cache_read"]
            + usage.cache_creation_tokens * prices["cache_creation"]
        ) / 1_000_000

    entry = {
        "month": month,
        "step": step,
        "provider": provider,
        "model": model,
        "timestamp": datetime.now().isoformat(),
        "input_tokens": usage.input_tokens,
        "output_tokens": usage.output_tokens,
        "cache_read_tokens": usage.cache_read_tokens,
        "cache_creation_tokens": usage.cache_creation_tokens,
        "cost_usd": cost_usd,
        "duration_ms": usage.duration_ms,
    }

    TOKEN_LOG.parent.mkdir(parents=True, exist_ok=True)
    with TOKEN_LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")

    cost = f"${cost_usd:.4f}" if cost_usd is not None else "cost unknown"
    return (
        f"[{month}] Tokens ({step}/{model}): "
        f"{usage.input_tokens:,} in + {usage.output_tokens:,} out | {cost}"
    )
