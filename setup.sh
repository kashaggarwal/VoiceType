#!/bin/bash
# VoiceType Setup Script
# Installs everything needed on a fresh Mac (Apple Silicon required)

set -e

echo ""
echo "╔══════════════════════════════════╗"
echo "║   VoiceType — Setup & Install    ║"
echo "╚══════════════════════════════════╝"
echo ""

# ── 1. Check Apple Silicon ─────────────────────────────────────────────────
ARCH=$(uname -m)
if [ "$ARCH" != "arm64" ]; then
    echo "❌ VoiceType requires an Apple Silicon Mac (M1/M2/M3/M4)."
    echo "   This machine reports: $ARCH (Intel is not supported)"
    echo "   MLX Whisper only runs on Apple Silicon GPUs."
    exit 1
fi
echo "✅ Apple Silicon detected ($ARCH)"

# ── 2. Check macOS version ─────────────────────────────────────────────────
OS_VER=$(sw_vers -productVersion | cut -d. -f1)
if [ "$OS_VER" -lt 13 ]; then
    echo "❌ VoiceType requires macOS 13 (Ventura) or later."
    echo "   Your macOS: $(sw_vers -productVersion)"
    exit 1
fi
echo "✅ macOS $(sw_vers -productVersion)"

# ── 3. Check available disk space (need at least 2 GB) ────────────────────
echo ""
echo "🔍 Checking disk space..."
FREE_KB=$(df -k "$HOME" | awk 'NR==2 {print $4}')
FREE_GB=$(echo "scale=1; $FREE_KB / 1048576" | bc)
REQUIRED_KB=2097152  # 2 GB in KB

if [ "$FREE_KB" -lt "$REQUIRED_KB" ]; then
    echo "❌ Not enough disk space."
    echo "   Available: ${FREE_GB} GB"
    echo "   Required:  ~2 GB (500 MB model + packages + breathing room)"
    echo ""
    echo "   Please free up space and run setup.sh again."
    echo "   Tips: Empty Trash, delete large files in Downloads,"
    echo "   or go to Apple Menu → About This Mac → Storage → Manage."
    exit 1
fi
echo "✅ Disk space OK (${FREE_GB} GB available)"

# ── 4. Check internet connectivity ────────────────────────────────────────
echo "🔍 Checking internet connection..."
if ! curl -s --max-time 5 https://huggingface.co > /dev/null 2>&1; then
    echo "❌ No internet connection detected."
    echo "   VoiceType needs internet once to download the AI model (~500 MB)."
    echo "   Please connect to WiFi and try again."
    exit 1
fi
echo "✅ Internet connection OK"

# ── 5. Install Homebrew if missing ─────────────────────────────────────────
echo ""
if ! command -v brew &>/dev/null && [ ! -f /opt/homebrew/bin/brew ]; then
    echo "📦 Installing Homebrew (this may take a few minutes)..."
    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
    eval "$(/opt/homebrew/bin/brew shellenv)"
else
    eval "$(/opt/homebrew/bin/brew shellenv)" 2>/dev/null || true
    echo "✅ Homebrew found ($(brew --version | head -1))"
fi

# ── 6. Install Python 3.14 via Homebrew ───────────────────────────────────
if ! /opt/homebrew/bin/python3.14 --version &>/dev/null; then
    echo ""
    echo "📦 Installing Python 3.14 via Homebrew..."
    brew install python@3.14
else
    echo "✅ Python $(/opt/homebrew/bin/python3.14 --version)"
fi

# ── 7. Create virtual environment ─────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

echo ""
echo "🐍 Creating virtual environment..."
rm -rf venv
/opt/homebrew/bin/python3.14 -m venv venv
echo "✅ venv created"

# ── 8. Install Python packages ────────────────────────────────────────────
echo ""
echo "📦 Installing packages (this may take a few minutes)..."
venv/bin/pip install --quiet --upgrade pip
venv/bin/pip install mlx-whisper sounddevice numpy pyperclip pynput \
                     pillow pystray pyobjc-framework-Cocoa pyobjc-framework-Quartz
echo "✅ Packages installed"

# ── 9. Verify all imports work ────────────────────────────────────────────
echo ""
echo "🔍 Verifying installation..."
venv/bin/python -c "
import mlx_whisper, sounddevice, pynput, pystray, AppKit, Quartz
print('✅ All packages verified OK')
" || {
    echo "❌ Package verification failed. Please check the error above and try running setup.sh again."
    exit 1
}

# ── 10. Fix app bundle permissions ────────────────────────────────────────
chmod +x "$SCRIPT_DIR/VoiceType.app/Contents/MacOS/VoiceType"
echo "✅ App permissions set"

# ── 11. Install Launch Agent (auto-start on login) ────────────────────────
PLIST="$HOME/Library/LaunchAgents/com.voicetype.menubar.plist"
mkdir -p "$HOME/Library/LaunchAgents"

cat > "$PLIST" << EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.voicetype.menubar</string>
    <key>ProgramArguments</key>
    <array>
        <string>/usr/bin/open</string>
        <string>${SCRIPT_DIR}/VoiceType.app</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <false/>
    <key>StandardOutPath</key>
    <string>/tmp/voicetype.log</string>
    <key>StandardErrorPath</key>
    <string>/tmp/voicetype.log</string>
</dict>
</plist>
EOF

launchctl unload "$PLIST" 2>/dev/null || true
launchctl load "$PLIST"
echo "✅ Launch Agent installed (VoiceType will auto-start on login)"

# ── 12. Download the Whisper model ────────────────────────────────────────
echo ""
echo "🤖 Downloading Whisper AI model (~500 MB, one-time only)..."
echo "   Please keep this window open — this may take 5–10 minutes"
echo "   depending on your internet speed..."
echo ""

venv/bin/python -c "
import mlx_whisper, numpy as np, sys

try:
    mlx_whisper.transcribe(
        np.zeros(16000, dtype='float32'),
        path_or_hf_repo='mlx-community/whisper-small-mlx',
        verbose=False
    )
    print('✅ Model downloaded and ready')
except OSError as e:
    if 'No space left' in str(e):
        print('')
        print('❌ Download failed: No space left on device.')
        print('   Please free up at least 1 GB of storage and run setup.sh again.')
        print('   Tip: Apple Menu → About This Mac → Storage → Manage')
        sys.exit(1)
    raise
" || exit 1

# ── 13. Launch the app ────────────────────────────────────────────────────
echo ""
echo "🚀 Launching VoiceType..."
open "$SCRIPT_DIR/VoiceType.app"

# ── 14. Final instructions ────────────────────────────────────────────────
echo ""
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║                  ✅ Installation Complete!                   ║"
echo "╠══════════════════════════════════════════════════════════════╣"
echo "║                                                              ║"
echo "║  Two permissions needed (one-time):                          ║"
echo "║                                                              ║"
echo "║  1. ACCESSIBILITY — for the Right ⌥ hotkey to work          ║"
echo "║     System Settings → Privacy & Security → Accessibility    ║"
echo "║     → click + → find VoiceType.app in this folder → Add     ║"
echo "║                                                              ║"
echo "║  2. MICROPHONE — auto-prompted on first recording            ║"
echo "║     Just click Allow when macOS asks                         ║"
echo "║                                                              ║"
echo "║  HOW TO USE:                                                 ║"
echo "║  • Look for the mic icon in your menu bar (top right)        ║"
echo "║  • Click it → Turn ON                                        ║"
echo "║  • Hold Right ⌥, speak, release → text pastes anywhere      ║"
echo "║                                                              ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""

# Open Accessibility settings automatically
open "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility"
