#!/bin/sh
# Weekly profile refresh: rebuild the token and commit charts, push them if anything changed.
# Run by ~/Library/LaunchAgents/com.malekhassan.profile-stats.plist; safe to run by hand too.
# Running at least monthly also keeps the per-repo ledger complete, because Claude Code
# deletes transcripts after about 30 days.
set -eu
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"
cd "$(dirname "$0")/.."

echo "== $(date '+%Y-%m-%d %H:%M') refresh"
git pull --rebase --quiet
python3 tools/build_profile.py
git add assets
if git diff --cached --quiet; then
	echo "no changes"
	exit 0
fi
git commit --quiet -m "Stats: weekly refresh ($(date +%Y-%m-%d))"
git push --quiet
echo "pushed $(git rev-parse --short HEAD)"
