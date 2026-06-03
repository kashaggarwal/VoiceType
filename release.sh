#!/bin/bash
# release.sh — cut a new VoiceType version in one command.
#
#   Usage:  ./release.sh 1.4 "what changed in this version"
#
#           arg 1 = new version number (e.g. 1.4)
#           arg 2 = short description of what changed (in quotes)
#
# What it does:
#   1. Bumps the version in VoiceType.spec, setup.py, and dashboard.py
#   2. Commits the change
#   3. Tags it (v1.4) and pushes everything to GitHub
#   4. Publishes a GitHub *Release* from that tag (the "Latest" badge)
#
# Notes:
#   - Commit messages and release notes are kept clean — NO "Generated with
#     Claude Code" / Co-Authored-By attribution.
#   - Build the .app separately with:  pyinstaller VoiceType.spec
#     (not usually needed — the app runs the source files directly.)

set -e  # stop on any error

VERSION="$1"
NOTE="$2"

if [ -z "$VERSION" ] || [ -z "$NOTE" ]; then
  echo "Usage: ./release.sh <version> \"<what changed>\""
  echo "Example: ./release.sh 1.4 \"new export feature, bug fixes\""
  exit 1
fi

cd "$(dirname "$0")"

# Safety: don't release with uncommitted leftover work you forgot about
echo "==> Files that will be included in this release:"
git status -s
echo ""

# 1. Bump version numbers everywhere they live
echo "==> Setting version to $VERSION ..."
sed -i '' -E "s/(\"CFBundleVersion\":[[:space:]]*\")[^\"]*/\1${VERSION}.0/" VoiceType.spec setup.py
sed -i '' -E "s/(\"CFBundleShortVersionString\":[[:space:]]*\")[^\"]*/\1${VERSION}/" VoiceType.spec setup.py
# Dashboard "About" version (single source of truth in dashboard.py)
sed -i '' -E "s/^VERSION = \"[^\"]*\"/VERSION = \"${VERSION}\"/" dashboard.py

# 2. Commit everything (clean message — no attribution)
git add -A
git commit -m "VoiceType v${VERSION} — ${NOTE}"

# 3. Tag and push
git tag "v${VERSION}"
git push origin main --tags

# 4. Publish a GitHub Release from the tag (makes it the "Latest" release).
#    Release notes = the description you passed. No attribution lines.
echo "==> Publishing GitHub Release v${VERSION} ..."
gh release create "v${VERSION}" \
  --title "VoiceType v${VERSION}" \
  --notes "## What's new in v${VERSION}

${NOTE}"

echo ""
echo "==> Done. v${VERSION} is committed, tagged, pushed, and published as the"
echo "    latest GitHub Release."
