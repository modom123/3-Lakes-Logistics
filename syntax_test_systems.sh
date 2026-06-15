#!/bin/bash
# 3 Lakes Logistics — Per-System Syntax Test Runner
# Covers: Website · Eagle Eye · Execution Engine · Hawk · Heavy Mobile · Light Mobile

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

ROOT="$(cd "$(dirname "$0")" && pwd)"
OVERALL_FAILED=0

# ── Helpers ────────────────────────────────────────────────────────────────────

check_js_file() {
  local f="$1"
  node --check "$f" 2>&1
  return $?
}

check_python_file() {
  local f="$1"
  python3 -m py_compile "$f" 2>&1
  return $?
}

check_json_file() {
  local f="$1"
  python3 -m json.tool "$f" > /dev/null 2>&1
  return $?
}

# Extract and check inline <script> blocks from an HTML file.
# Skips external scripts (src=) and non-JS types (text/babel, text/template, etc.)
check_html_scripts() {
  local html="$1"
  python3 - "$html" <<'PYEOF'
import sys, re, subprocess, os, tempfile

html_file = sys.argv[1]
with open(html_file, 'r', encoding='utf-8', errors='replace') as f:
    content = f.read()

NON_JS = re.compile(r'\btype\s*=\s*["\'](?!(?:text/javascript|application/javascript)\b)[^"\']+["\']', re.IGNORECASE)
pattern = re.compile(r'<script([^>]*)>(.*?)</script>', re.DOTALL | re.IGNORECASE)

errors = []
for i, (attrs, block) in enumerate(pattern.findall(content)):
    if 'src' in attrs.lower() or NON_JS.search(attrs):
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
        err_lines = result.stderr.strip().splitlines()
        errors.append((i+1, err_lines[:5]))

if errors:
    fname = os.path.basename(html_file)
    for block_num, lines in errors:
        print(f"  ✗ {fname} — script block #{block_num}:")
        for line in lines:
            print(f"      {line}")
    sys.exit(1)
sys.exit(0)
PYEOF
  return $?
}

# Run all checks for one system. Args: system_name file1 file2 ...
run_system() {
  local system="$1"; shift
  local files=("$@")
  local sys_failed=0
  local checked=0

  echo ""
  echo -e "${CYAN}${BOLD}┌─ $system ─────────────────────────────────────────────${NC}"

  for f in "${files[@]}"; do
    local abs="$ROOT/$f"
    if [ ! -f "$abs" ]; then
      echo -e "  ${YELLOW}⚠ Not found: $f${NC}"
      continue
    fi
    checked=$((checked+1))
    local ext="${f##*.}"
    local result=0
    local label="$(basename "$f")"

    case "$ext" in
      js)
        out=$(check_js_file "$abs" 2>&1)
        result=$?
        ;;
      py)
        out=$(check_python_file "$abs" 2>&1)
        result=$?
        ;;
      json)
        out=$(check_json_file "$abs" 2>&1)
        result=$?
        ;;
      html)
        out=$(check_html_scripts "$abs" 2>&1)
        result=$?
        ;;
      *)
        out="Skipped (unknown type)"
        result=0
        ;;
    esac

    if [ $result -eq 0 ]; then
      echo -e "  ${GREEN}✓${NC} $label"
    else
      echo -e "  ${RED}✗${NC} $label"
      echo "$out" | sed 's/^/      /'
      sys_failed=1
      OVERALL_FAILED=1
    fi
  done

  if [ $sys_failed -eq 0 ]; then
    echo -e "${CYAN}└─ ${GREEN}PASS${NC} ${CYAN}($checked files checked)${NC}"
  else
    echo -e "${CYAN}└─ ${RED}FAIL${NC}"
  fi

  return $sys_failed
}

# ── Also check all Python files in a directory ─────────────────────────────────
run_python_dir() {
  local label="$1"
  local dir="$ROOT/$2"
  if [ ! -d "$dir" ]; then
    echo -e "  ${YELLOW}⚠ Dir not found: $2${NC}"
    return 0
  fi
  local failed=0
  while IFS= read -r -d '' pyfile; do
    out=$(check_python_file "$pyfile" 2>&1)
    if [ $? -ne 0 ]; then
      echo -e "  ${RED}✗${NC} $(basename "$pyfile")"
      echo "$out" | sed 's/^/      /'
      failed=1
      OVERALL_FAILED=1
    else
      echo -e "  ${GREEN}✓${NC} $(basename "$pyfile")"
    fi
  done < <(find "$dir" -name "*.py" -not -path "*/__pycache__/*" -print0)
  return $failed
}

# ══════════════════════════════════════════════════════════════════════════════
echo ""
echo -e "${BOLD}============================================================${NC}"
echo -e "${BOLD}  3 Lakes Logistics — Per-System Syntax Tests              ${NC}"
echo -e "${BOLD}============================================================${NC}"

# ── 1. WEBSITE ────────────────────────────────────────────────────────────────
run_system "WEBSITE" \
  "website.html" \
  "index.html" \
  "shared/config.js" \
  "shared/tk.js"

# ── 2. EAGLE EYE ──────────────────────────────────────────────────────────────
run_system "EAGLE EYE" \
  "eagleeye.html"

# ── 3. EXECUTION ENGINE ───────────────────────────────────────────────────────
echo ""
echo -e "${CYAN}${BOLD}┌─ EXECUTION ENGINE ─────────────────────────────────────${NC}"
run_python_dir "Execution Engine Backend" "backend/app/execution_engine"
# The front-end lives inside Eagle Eye (already checked above)
echo -e "  ${GREEN}✓${NC} Front-end: embedded in Eagle Eye (checked above)"
echo -e "${CYAN}└─ done${NC}"

# ── 4. HAWK ───────────────────────────────────────────────────────────────────
run_system "HAWK (Desktop Driver Portal)" \
  "hawk.html" \
  "driver-pwa/index.html" \
  "driver-pwa/login.html" \
  "driver-pwa/sw.js" \
  "driver-pwa/manifest.json"

# ── 5. HEAVY MOBILE ───────────────────────────────────────────────────────────
run_system "HEAVY MOBILE (CDL Driver PWA)" \
  "driver-heavy.html" \
  "driver-pwa/index.html" \
  "driver-pwa/login.html" \
  "driver-pwa/sw.js" \
  "driver-pwa/manifest.json"

# ── 6. LIGHT MOBILE ───────────────────────────────────────────────────────────
run_system "LIGHT MOBILE (Light Fleet PWA)" \
  "light-fleet.html" \
  "light-fleet-marketing.html" \
  "driver-pwa/lf.html" \
  "driver-pwa/login-lf.html" \
  "driver-pwa/manifest-lf.json"

# ── Overall Result ─────────────────────────────────────────────────────────────
echo ""
echo -e "${BOLD}============================================================${NC}"
if [ $OVERALL_FAILED -eq 1 ]; then
  echo -e "${RED}${BOLD}  RESULT: One or more systems have syntax errors. Fix above.${NC}"
  exit 1
else
  echo -e "${GREEN}${BOLD}  RESULT: All systems passed syntax checks!${NC}"
  exit 0
fi
