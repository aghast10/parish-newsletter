#!/usr/bin/env bash
# Compose the parish newsletter using Claude Sonnet.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
TODAY=$(date +%Y-%m-%d)
MONTH=$(date +%Y-%m)
MONTH_NAME=$(date +%B)
YEAR=$(date +%Y)
DRAFT_FILE="$PROJECT_DIR/data/drafts/${MONTH}-draft.html"

SUBMISSIONS_DIR="$PROJECT_DIR/data/submissions/$MONTH"
PROMPT_TEMPLATE="$PROJECT_DIR/prompts/compose.md"

if [ ! -d "$SUBMISSIONS_DIR" ] || [ -z "$(ls -A "$SUBMISSIONS_DIR"/*.md 2>/dev/null)" ]; then
    echo "[$TODAY] No submissions found for $MONTH. Nothing to compose."
    exit 1
fi

# Build prompt with template substitution
PROMPT=$(sed "s/{{MONTH}}/$MONTH_NAME/g; s/{{YEAR}}/$YEAR/g" "$PROMPT_TEMPLATE")

# Read style guide
STYLE=""
if [ -f "$PROJECT_DIR/prompts/style.md" ]; then
    STYLE=$(cat "$PROJECT_DIR/prompts/style.md")
fi

# Read HTML template
TEMPLATE=""
if [ -f "$PROJECT_DIR/prompts/template.html" ]; then
    TEMPLATE=$(cat "$PROJECT_DIR/prompts/template.html")
fi

# Concatenate all group submissions
SUBMISSIONS=""
for f in "$SUBMISSIONS_DIR"/*.md; do
    GROUP_NAME=$(basename "$f" .md)
    SUBMISSIONS+="
=== $GROUP_NAME ===
$(cat "$f")

"
done

mkdir -p "$(dirname "$DRAFT_FILE")"

echo "[$TODAY] Composing newsletter for $MONTH with Claude..."

cd "$PROJECT_DIR"
unset CLAUDECODE
# Sin herramientas: los informes son correos de fuera y podrían llevar instrucciones
# para el modelo. `--allowedTools` no quita nada (~/.claude/settings.json permite
# Bash(*)); `--tools ""` sí. El HTML vuelve en la respuesta y lo guarda este script.
CLAUDE_JSON=$(printf '%s\n\n## Estilo\n%s\n\n## Plantilla HTML de referencia\n```html\n%s\n```\n\n## Informes de los grupos\n%s' \
    "$PROMPT" "$STYLE" "$TEMPLATE" "$SUBMISSIONS" | \
    claude -p \
    --model claude-sonnet-4-6 \
    --tools "" \
    --output-format json)
echo "$CLAUDE_JSON" | python3 "$SCRIPT_DIR/log_tokens.py" "$MONTH" "compose" sonnet
echo "$CLAUDE_JSON" | python3 -c '
import json, re, sys
html = (json.load(sys.stdin).get("result") or "").strip()
html = re.sub(r"^```(?:html)?\s*|\s*```$", "", html)
if "</html>" in html.lower():
    open(sys.argv[1], "w", encoding="utf-8").write(html + "\n")
' "$DRAFT_FILE"

if [ -f "$DRAFT_FILE" ]; then
    echo "[$TODAY] Draft saved: $DRAFT_FILE"
else
    echo "[$TODAY] Warning: draft file not created."
fi
