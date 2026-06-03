#!/bin/bash
# release.sh — cut a new VoiceType version in one command.
#
#   Usage:  ./release.sh 1.3 "HUD redesign, faster startup"
#
#           arg 1 = new version number (e.g. 1.3)
#           arg 2 = short description of what changed (in quotes)
#
# What it does:
#   1. Bumps the version in VoiceType.spec and setup.py
#   2. Commits the change
#   3. Tags it (v1.3) and pushes everything to GitHub
#
# Build the .app separately with:  pyinstaller VoiceType.spec

set -e  # stop on any error

VERSION="$1"
NOTE="$2"

if [ -z "$VERSION" ] || [ -z "$NOTE" ]; then
  echo "Usage: ./release.sh <version> \"<what changed>\""
  echo "Example: ./release.sh 1.3 \"HUD redesign, faster startup\""
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

# 2. Commit everything
git add -A
git commit -m "VoiceType v${VERSION} — ${NOTE}"

# 3. Tag and push
git tag "v${VERSION}"
git push origin main --tags

echo ""
echo "==> Done. v${VERSION} is committed, tagged, and pushed to GitHub."
echo "    To rebuild the app:  pyinstaller VoiceType.spec"
