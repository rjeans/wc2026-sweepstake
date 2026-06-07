#!/usr/bin/env bash
# Daily WC2026 sweepstake refresh:
#   1. Pull latest results from ESPN
#   2. Recompute standings (skipped pre-draw, when allocation.csv doesn't exist)
#   3. Sync the four CSVs into the jeansy.org repo
#   4. Commit and push (only if anything actually changed) -> Cloudflare rebuild
set -e

SWEEPSTAKE_DIR="$HOME/Development/sweepstake"
JEANSY_DIR="$HOME/Development/jeansy.org"

cd "$SWEEPSTAKE_DIR"

echo "[1/5] Fetching results from ESPN..."
uv run fetch_results.py

if [ -f allocation.csv ]; then
  echo "[2/5] Computing standings..."
  uv run scoring.py --alloc allocation.csv --results results.csv --output standings.csv
else
  echo "[2/5] No allocation.csv yet - skipping scoring (pre-draw)."
fi

echo "[3/5] Syncing into jeansy.org..."
cd "$JEANSY_DIR"
bash scripts/sync-sweepstake.sh

echo "[4/5] Staging changes..."
# Path-bounded; only the four CSVs the sync script writes live in this dir.
git add --all src/data/wc2026/

if git diff --cached --quiet -- src/data/wc2026/; then
  echo "[5/5] No changes to commit - done."
  exit 0
fi

echo "[5/5] Committing and pushing..."
git commit -m "wc2026: $(date +%Y-%m-%d) update"
git push
echo "Done. Cloudflare will rebuild in 30-60s; live at https://jeansy.org/wc2026"
