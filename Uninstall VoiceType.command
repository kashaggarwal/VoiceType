#!/bin/bash
# VoiceType — Uninstaller

cd "$(dirname "$0")"
VOICETYPE_DIR="$(pwd)"

clear
echo ""
echo "╔══════════════════════════════════════════════════════════════════╗"
echo "║                                                                  ║"
echo "║           🗑️   VoiceType — Uninstaller                          ║"
echo "║                                                                  ║"
echo "╚══════════════════════════════════════════════════════════════════╝"
echo ""
echo "  This will remove VoiceType from your Mac."
echo ""
echo "  What will be removed:"
echo "    • Auto-start at login (LaunchAgent)"
echo "    • Python packages and virtual environment"
echo "    • VoiceType preferences and stats (~/.voicetype)"
echo ""
echo "  What will NOT be removed (optional — saves disk space):"
echo "    • The AI model cache (~500 MB in ~/.cache/huggingface)"
echo "    • The VoiceType folder itself"
echo ""

echo "  Are you sure you want to uninstall VoiceType? (yes/no)"
read -r CONFIRM
if [ "$CONFIRM" != "yes" ] && [ "$CONFIRM" != "y" ]; then
    echo ""
    echo "  Uninstall cancelled. Nothing was changed."
    echo ""
    echo "  Press Enter to close."
    read -r
    exit 0
fi

echo ""
echo "  Uninstalling..."
echo ""

# Kill running VoiceType processes
echo "  • Stopping VoiceType..."
pkill -f "menubar.py" 2>/dev/null || true
pkill -f "worker.py" 2>/dev/null || true
pkill -f "VoiceType" 2>/dev/null || true
sleep 1

# Remove LaunchAgent
PLIST="$HOME/Library/LaunchAgents/com.voicetype.menubar.plist"
if [ -f "$PLIST" ]; then
    echo "  • Removing auto-start (LaunchAgent)..."
    launchctl unload "$PLIST" 2>/dev/null || true
    rm -f "$PLIST"
    echo "    ✅ Done"
else
    echo "  • LaunchAgent not found (already removed)"
fi

# Remove venv
if [ -d "$VOICETYPE_DIR/venv" ]; then
    echo "  • Removing Python packages..."
    rm -rf "$VOICETYPE_DIR/venv"
    echo "    ✅ Done"
fi

# Remove stats and config
if [ -d "$HOME/.voicetype" ]; then
    echo "  • Removing VoiceType data (~/.voicetype)..."
    rm -rf "$HOME/.voicetype"
    echo "    ✅ Done"
fi

echo ""
echo "  ✅ VoiceType has been uninstalled."
echo ""

# Offer to delete the AI model (large)
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "  The AI model is still saved at:"
echo "    ~/.cache/huggingface/hub/"
echo ""
echo "  Deleting it frees up 500 MB – 1.5 GB of disk space."
echo "  If you reinstall VoiceType later, it will re-download the model."
echo ""
echo "  Delete the AI model cache? (yes/no)"
read -r DELETE_MODEL

if [ "$DELETE_MODEL" = "yes" ] || [ "$DELETE_MODEL" = "y" ]; then
    echo "  • Deleting model cache..."
    rm -rf "$HOME/.cache/huggingface/hub/models--mlx-community--whisper-small-mlx"
    rm -rf "$HOME/.cache/huggingface/hub/models--mlx-community--whisper-medium-mlx"
    rm -rf "$HOME/.cache/huggingface/hub/models--mlx-community--whisper-large-mlx"
    echo "  ✅ Model cache deleted"
else
    echo "  ✓ Model cache kept (you can delete it manually later if needed)"
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "  Uninstall complete. You can now delete the VoiceType folder."
echo ""
echo "  To remove it, drag the VoiceType folder to the Trash."
echo ""
echo "  Press Enter to close."
read -r
