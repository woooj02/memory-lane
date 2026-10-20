#!/usr/bin/env bash
# Saturday go/no-go: is the Bee data reachable, and is the Nepali usable?
#   ./check-bee.sh            run every check
#   ./check-bee.sh live       also watch the live stream for 60s (speak near the watch)
set -uo pipefail
cd "$(dirname "$0")"
ok(){ printf '  \033[32mPASS\033[0m %s\n' "$1"; }
bad(){ printf '  \033[31mFAIL\033[0m %s\n     → %s\n' "$1" "$2"; FAILED=1; }
FAILED=0

echo "1. Node 18 or newer (the bee CLI needs it)"
NODE_MAJOR=$(node -v 2>/dev/null | sed 's/v\([0-9]*\).*/\1/')
if [ "${NODE_MAJOR:-0}" -ge 18 ]; then ok "node $(node -v)"; elif bee version >/dev/null 2>&1; then ok "node $(node -v), but bee runs"; else
  bad "node ${NODE_MAJOR:-missing}" "nvm install 20 && nvm use 20"; fi

echo "2. bee CLI installed"
if command -v bee >/dev/null; then ok "$(bee version 2>/dev/null | head -1)"; else
  bad "bee not found" "npm install -g @beeai/cli"; fi

echo "3. Logged in to Bee (Developer Mode on in the app: tap the version 5 times)"
if bee me --json >/dev/null 2>&1; then ok "bee me works"; else
  bad "not logged in" "bee login   (approve it in the Bee app on the iPhone)"; fi

echo "4. Recordings exist"
LIST=$(bee conversations list --limit 5 --json 2>/dev/null)
COUNT=$(printf '%s' "$LIST" | python3 -c 'import json,sys; print(len(json.load(sys.stdin).get("conversations",[])))' 2>/dev/null || echo 0)
if [ "$COUNT" -gt 0 ]; then ok "$COUNT recent conversations"; else
  bad "no conversations yet" "record 1 minute of normal talk (50+ words) on the watch, wait a few minutes"; fi

echo "5. Is the newest transcript in Nepali script?"
if [ "$COUNT" -gt 0 ]; then
  ID=$(printf '%s' "$LIST" | python3 -c 'import json,sys; print(json.load(sys.stdin)["conversations"][0]["id"])')
  bee conversations get "$ID" --json > data/last-conversation.json 2>/dev/null
  python3 - data/last-conversation.json <<'PY'
import json, sys
conv = json.load(open(sys.argv[1])).get("conversation", {})
utts = [u for t in conv.get("transcriptions", []) for u in t.get("utterances", [])]
text = " ".join(u.get("text", "") for u in utts)
deva = sum("ऀ" <= ch <= "ॿ" for ch in text)
letters = sum(ch.isalpha() for ch in text) or 1
print(f"     conversation {conv.get('id')}: {len(utts)} lines, {len(text.split())} words, "
      f"{100*deva//letters}% Devanagari")
print(f"     Bee summary: {conv.get('summary') or '(none yet)'}")
for u in utts[:6]:
    print(f"     {u.get('speaker')}: {u.get('text')}")
sys.exit(0 if deva / letters > 0.5 else 3)
PY
  case $? in
    0) ok "mostly Nepali script. Read the lines above: are they what was said?";;
    *) bad "little or no Nepali script" "Bee may not support Nepali. Read the lines above; if they're Hindi or gibberish, use the English fallback (see SATURDAY.md)";;
  esac
fi

if [ "${1:-}" = "live" ]; then
  echo "6. Live stream: speak near the watch for 60s"
  timeout 60 bee stream --types new-utterance || true
fi

echo
[ $FAILED = 0 ] && echo "GO: run ./run.sh and open http://127.0.0.1:8110/family, then press Sync." \
                || echo "Fix the FAIL lines above, then run this again."
