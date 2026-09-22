#!/usr/bin/env python3
"""Parse claude -p --output-format json output, log token usage to data/token_log.jsonl.

Usage: log_tokens.py MONTH STEP [MODEL] [--extract]
  MODEL: sonnet (default), opus, haiku
  --extract: also print the 'result' text to stdout
"""

import json
import sys
from datetime import datetime
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent
TOKEN_LOG = PROJECT_DIR / "data" / "token_log.jsonl"

PRICING = {
    "sonnet": {"input": 3.00,  "output": 15.00, "cache_read": 0.30, "cache_creation": 3.75},
    "opus":   {"input": 15.00, "output": 75.00, "cache_read": 1.50, "cache_creation": 18.75},
    "haiku":  {"input": 0.80,  "output": 4.00,  "cache_read": 0.08, "cache_creation": 1.00},
}


def main():
    month = sys.argv[1] if len(sys.argv) > 1 else datetime.now().strftime("%Y-%m")
    step = sys.argv[2] if len(sys.argv) > 2 else "compose"
    model = sys.argv[3] if len(sys.argv) > 3 and not sys.argv[3].startswith("--") else "sonnet"
    extract_mode = "--extract" in sys.argv

    prices = PRICING.get(model, PRICING["sonnet"])

    raw = sys.stdin.read().strip()
    if not raw:
        print(f"[{month}] Token log ({step}): no JSON from claude", file=sys.stderr)
        return

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"[{month}] Token log ({step}): JSON parse error: {e}", file=sys.stderr)
        return

    if extract_mode:
        print(data.get("result", ""))

    usage = data.get("usage", {})
    input_tokens = usage.get("input_tokens", 0)
    output_tokens = usage.get("output_tokens", 0)
    cache_read = usage.get("cache_read_input_tokens", 0)
    cache_creation = usage.get("cache_creation_input_tokens", 0)
    duration_ms = data.get("duration_ms", 0)
    num_turns = data.get("num_turns", 0)
    total_tokens = input_tokens + output_tokens

    cost_usd = data.get("cost_usd") or (
        input_tokens * prices["input"] / 1_000_000
        + output_tokens * prices["output"] / 1_000_000
        + cache_read * prices["cache_read"] / 1_000_000
        + cache_creation * prices["cache_creation"] / 1_000_000
    )

    entry = {
        "month": month,
        "step": step,
        "model": model,
        "timestamp": datetime.now().isoformat(),
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cache_read_tokens": cache_read,
        "cache_creation_tokens": cache_creation,
        "total_tokens": total_tokens,
        "cost_usd": cost_usd,
        "duration_ms": duration_ms,
        "num_turns": num_turns,
    }

    TOKEN_LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(TOKEN_LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")

    summary = (
        f"[{month}] Tokens ({step}/{model}): "
        f"{input_tokens:,} in + {output_tokens:,} out = {total_tokens:,} total | "
        f"${cost_usd:.4f}"
    )
    print(summary, file=sys.stderr if extract_mode else sys.stdout)


if __name__ == "__main__":
    main()
