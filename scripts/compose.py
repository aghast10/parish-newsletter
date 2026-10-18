#!/usr/bin/env python3
"""Compose the parish newsletter: an LLM writes the text, template.html sets the design.

Usage: compose.py [--month YYYY-MM] [--notes "instrucciones del administrador"]

The model returns JSON (greeting, one section per group, closing) with light markup
(blank-line paragraphs, **bold**, *italics*, "- " lists). This script escapes it, turns it into
HTML and fills prompts/template.html, so the design never drifts and nothing from
the submitted emails reaches the page as raw HTML.
"""

import argparse
import html
import itertools
import re

from common import (
    DRAFTS_DIR, PROJECT_DIR, fail, load_config, log, month_label, submission_status,
    today,
)
from llm import LLMError, complete_json
from log_tokens import log_usage

PROMPTS_DIR = PROJECT_DIR / "prompts"

LINK_STYLE = "color:#b30c3c;text-decoration:none;"
LINK_RE = re.compile(r"(https?://[^\s<>\"]+[^\s<>\".,;:!?)])|([\w.+-]+@[\w-]+(?:\.[\w-]+)+)")


# ── Markup → HTML ───────────────────────────────────────────────────

def _link(match):
    url, address = match.groups()
    if url:
        return f'<a href="{url}" target="_blank" style="{LINK_STYLE}">{url}</a>'
    return f'<a href="mailto:{address}" style="{LINK_STYLE}">{address}</a>'


def inline(text):
    """Escape text, then apply **bold**, *italics* and auto-link URLs and emails."""
    out = html.escape(text.strip(), quote=True)
    out = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", out)
    out = re.sub(r"(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?![\w*])", r"<em>\1</em>", out)
    return LINK_RE.sub(_link, out)


def blocks(text):
    """Blank-line separated paragraphs and runs of '- ' lines → <p>/<ul>."""
    parts = []
    for block in re.split(r"\n\s*\n", text.strip()):
        lines = [l.strip() for l in block.splitlines() if l.strip()]
        for is_item, run in itertools.groupby(lines, key=lambda l: l.startswith("- ")):
            run = list(run)
            if is_item:
                items = "".join(f'<li style="margin:0 0 4px;">{inline(l[2:])}</li>' for l in run)
                parts.append(f'<ul style="margin:0 0 12px;padding-left:20px;">{items}</ul>')
            else:
                parts.append(f'<p style="margin:0 0 12px;">{"<br>".join(inline(l) for l in run)}</p>')
    return "\n        ".join(parts)


# ── Template ────────────────────────────────────────────────────────

def fill(template, values):
    for key, value in values.items():
        template = template.replace("{{" + key + "}}", value)
    return template


def render(content, groups_by_id, month_name, year):
    template = (PROMPTS_DIR / "template.html").read_text(encoding="utf-8")
    head, rest = template.split("<!-- SECTION", 1)
    section_tpl, tail = rest.split("<!-- /SECTION -->", 1)
    section_tpl = section_tpl.split("-->", 1)[1]

    # Template order (config order), one section per group, unknown ids dropped.
    texts = {}
    for section in content.get("sections", []):
        gid = section.get("group_id")
        if gid in groups_by_id and section.get("text", "").strip():
            texts.setdefault(gid, section["text"])
        else:
            log(f"Warning: ignoring section for unknown or empty group {gid!r}")

    sections = "".join(
        fill(section_tpl, {
            "GROUP_EMOJI": html.escape(group.get("emoji", "✦")),
            "GROUP_NAME": html.escape(group["name"]),
            "GROUP_CONTENT": blocks(texts[gid]),
        })
        for gid, group in groups_by_id.items() if gid in texts
    )
    if not sections:
        fail("The model returned no usable sections.")

    return fill(head + sections + tail, {
        "MONTH": month_name.capitalize(),
        "YEAR": str(year),
        "GREETING": inline(content.get("greeting", "")),
        "CLOSING": inline(content.get("closing", "")),
    })


# ── LLM ─────────────────────────────────────────────────────────────

def content_schema(group_ids):
    return {
        "type": "object",
        "properties": {
            "greeting": {"type": "string"},
            "sections": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "group_id": {"type": "string", "enum": group_ids},
                        "text": {"type": "string"},
                    },
                    "required": ["group_id", "text"],
                    "additionalProperties": False,
                },
            },
            "closing": {"type": "string"},
        },
        "required": ["greeting", "sections", "closing"],
        "additionalProperties": False,
    }


def build_prompts(submitted, month_name, year, notes):
    """(system, user): instructions in the system prompt, the emails in the user turn."""
    system = fill((PROMPTS_DIR / "compose.md").read_text(encoding="utf-8"),
                  {"MONTH": month_name, "YEAR": str(year)})
    system += "\n\n## Estilo\n" + (PROMPTS_DIR / "style.md").read_text(encoding="utf-8")
    if notes:
        system += f"\n\n## Correcciones del administrador\nAplica estas indicaciones:\n{notes}\n"

    user = "## Informes de los grupos\n\n" + "\n".join(
        f"=== {g['name']} (id: {g['id']}) ===\n{path.read_text(encoding='utf-8')}\n"
        for g, path in submitted
    )
    return system, user


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--month", default=today.strftime("%Y-%m"))
    parser.add_argument("--notes", default="", help="corrections for the model to apply")
    args = parser.parse_args()

    month_name, year = month_label(args.month)
    config = load_config()
    groups = config.get("groups", [])
    submitted = [(g, p) for g, p in submission_status(groups, args.month) if p]
    if not submitted:
        fail(f"No submissions found for {args.month}. Nothing to compose.")

    llm_cfg = config.get("llm", {})
    provider, model = llm_cfg.get("provider", "anthropic"), llm_cfg.get("model", "")
    log(f"Composing newsletter for {args.month} with {provider}/{model} ({len(submitted)} groups)...")
    system, user = build_prompts(submitted, month_name, year, args.notes)
    try:
        content, usage = complete_json(llm_cfg, system, user,
                                       content_schema([g["id"] for g, _ in submitted]),
                                       "newsletter_content")
    except LLMError as e:
        fail(str(e))
    print(log_usage(usage, args.month, "compose", provider, model))

    html_out = render(content, {g["id"]: g for g, _ in submitted}, month_name, year)
    DRAFTS_DIR.mkdir(parents=True, exist_ok=True)
    draft_file = DRAFTS_DIR / f"{args.month}-draft.html"
    draft_file.write_text(html_out, encoding="utf-8")
    log(f"Draft saved: {draft_file}")


if __name__ == "__main__":
    main()
