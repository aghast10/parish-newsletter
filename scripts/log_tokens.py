"""Log token usage of a `claude -p --output-format json` call to data/token_log.jsonl."""

import json
from datetime import datetime

from common import PROJECT_DIR

TOKEN_LOG = PROJECT_DIR / "data" / "token_log.jsonl"

# Fallback only: the CLI reports total_cost_usd itself.
PRICING = {
    "sonnet": {"input": 3.00,  "output": 15.00, "cache_read": 0.30, "cache_creation": 3.75},
    "opus":   {"input": 15.00, "output": 75.00, "cache_read": 1.50, "cache_creation": 18.75},
    "haiku":  {"input": 0.80,  "output": 4.00,  "cache_read": 0.08, "cache_creation": 1.00},
}


def log_usage(data, month, step, model="sonnet"):
    """Append one entry for the parsed CLI JSON `data` and return a summary line."""
    usage = data.get("usage", {})
    input_tokens = usage.get("input_tokens", 0)
    output_tokens = usage.get("output_tokens", 0)
    cache_read = usage.get("cache_read_input_tokens", 0)
    cache_creation = usage.get("cache_creation_input_tokens", 0)

    prices = PRICING.get(model, PRICING["sonnet"])
    cost_usd = data.get("total_cost_usd") or (
        input_tokens * prices["input"]
        + output_tokens * prices["output"]
        + cache_read * prices["cache_read"]
        + cache_creation * prices["cache_creation"]
    ) / 1_000_000

    entry = {
        "month": month,
        "step": step,
        "model": model,
        "timestamp": datetime.now().isoformat(),
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cache_read_tokens": cache_read,
        "cache_creation_tokens": cache_creation,
        "total_tokens": input_tokens + output_tokens,
        "cost_usd": cost_usd,
        "duration_ms": data.get("duration_ms", 0),
        "num_turns": data.get("num_turns", 0),
    }

    TOKEN_LOG.parent.mkdir(parents=True, exist_ok=True)
    with TOKEN_LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")

    return (
        f"[{month}] Tokens ({step}/{model}): "
        f"{input_tokens:,} in + {output_tokens:,} out | ${cost_usd:.4f}"
    )
