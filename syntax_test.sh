#!/bin/bash
# 3 Lakes Logistics — Unified Syntax Test Runner
# Checks Python, JSON, JavaScript (.js files), and inline <script> blocks in HTML files.

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'
FAILED=0
WARNINGS=0

echo "========================================="
echo " 3 Lakes Logistics — Syntax Test Runner "
echo "========================================="

# ── 1. Python ──────────────────────────────
echo -e "\n[1/4] Checking Python Syntax..."
if command -v python3 &> /dev/null; then
  python3 -m compileall -q . 2>&1 | grep -v "^Listing\|^Compiling\|__pycache__" | head -40
  if [ ${PIPESTATUS[0]} -eq 0 ]; then
    echo -e "${GREEN}✓ All Python files passed.${NC}"
  else
    echo -e "${RED}✗ Python syntax errors detected!${NC}"
    FAILED=1
  fi
else
  echo -e "${YELLOW}⚠ python3 not found — skipping.${NC}"
  WARNINGS=$((WARNINGS+1))
fi

# ── 2. JSON ────────────────────────────────
echo -e "\n[2/4] Checking JSON Validity..."
JSON_FAILED=0
while IFS= read -r -d '' json_file; do
  python3 -m json.tool "$json_file" > /dev/null 2>&1
  if [ $? -ne 0 ]; then
    echo -e "${RED}  ✗ Invalid JSON: $json_file${NC}"
    JSON_FAILED=1
    FAILED=1
  fi
done < <(find . -name "*.json" \
  -not -path "*/node_modules/*" \
  -not -path "*/.git/*" \
  -not -path "*/__pycache__/*" \
  -print0)
if [ $JSON_FAILED -eq 0 ]; then
  echo -e "${GREEN}✓ All JSON files are valid.${NC}"
fi

# ── 3. JavaScript (.js files) ──────────────
echo -e "\n[3/4] Checking JavaScript (.js files)..."
JS_FAILED=0
JS_COUNT=0
while IFS= read -r -d '' js_file; do
  node --check "$js_file" 2>&1
  if [ $? -ne 0 ]; then
    JS_FAILED=1
    FAILED=1
  fi
  JS_COUNT=$((JS_COUNT+1))
done < <(find . -name "*.js" \
  -not -path "*/node_modules/*" \
  -not -path "*/.git/*" \
  -not -path "*/play-store-graphics/*" \
  -print0)
if [ $JS_FAILED -eq 0 ]; then
  echo -e "${GREEN}✓ All $JS_COUNT .js files passed.${NC}"
fi

# ── 4. Inline <script> blocks in HTML ──────
echo -e "\n[4/4] Checking inline <script> blocks in HTML files..."
HTML_FAILED=0
HTML_COUNT=0
SCRIPT_ERRORS=0

while IFS= read -r -d '' html_file; do
  HTML_COUNT=$((HTML_COUNT+1))
  # Extract each <script>...</script> block (excluding src= external scripts)
  python3 - "$html_file" <<'PYEOF'
import sys, re, subprocess, os, tempfile

html_file = sys.argv[1]
with open(html_file, 'r', encoding='utf-8', errors='replace') as f:
    content = f.read()

# Match <script> blocks that are standard JS (no src=, no non-JS type=)
# Skips type="text/babel", type="text/template", type="module" (usually external), etc.
NON_JS_TYPES = re.compile(r'\btype\s*=\s*["\'](?!(?:text/javascript|application/javascript)\b)[^"\']+["\']', re.IGNORECASE)
pattern = re.compile(r'<script([^>]*)>(.*?)</script>', re.DOTALL | re.IGNORECASE)
matches = pattern.findall(content)

errors_found = False
for i, (attrs, block) in enumerate(matches):
    # Skip external scripts (src=) and non-JS types (text/babel, text/template, etc.)
    if 'src' in attrs.lower():
        continue
    if NON_JS_TYPES.search(attrs):
        continue
    stripped = block.strip()
    if not stripped:
        continue
    with tempfile.NamedTemporaryFile(mode='w', suffix='.js', delete=False, encoding='utf-8') as tmp:
        tmp.write(stripped)
        tmp_path = tmp.name
    result = subprocess.run(['node', '--check', tmp_path], capture_output=True, text=True)
    os.unlink(tmp_path)
    if result.returncode != 0:
        # Map line number back to HTML file
        err = result.stderr.strip()
        print(f"  ✗ {html_file} — inline script block #{i+1}:")
        for line in err.splitlines()[:4]:
            print(f"    {line}")
        errors_found = True

sys.exit(1 if errors_found else 0)
PYEOF

  if [ $? -ne 0 ]; then
    HTML_FAILED=1
    SCRIPT_ERRORS=$((SCRIPT_ERRORS+1))
    FAILED=1
  fi
done < <(find . -name "*.html" \
  -not -path "*/node_modules/*" \
  -not -path "*/.git/*" \
  -print0)

if [ $HTML_FAILED -eq 0 ]; then
  echo -e "${GREEN}✓ All $HTML_COUNT HTML files — inline scripts clean.${NC}"
else
  echo -e "${RED}✗ Inline script errors found in $SCRIPT_ERRORS HTML file(s).${NC}"
fi

# ── Summary ────────────────────────────────
echo ""
echo "-----------------------------------------"
if [ $FAILED -eq 1 ]; then
  echo -e "${RED}RESULT: Syntax tests FAILED. Fix errors above and re-run.${NC}"
  exit 1
else
  if [ $WARNINGS -gt 0 ]; then
    echo -e "${YELLOW}RESULT: All tests PASSED (with $WARNINGS skipped check(s)).${NC}"
  else
    echo -e "${GREEN}RESULT: All syntax tests PASSED!${NC}"
  fi
  exit 0
fi
