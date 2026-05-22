#!/bin/bash
# ╔══════════════════════════════════════════════════════════════════════╗
# ║           VoiceType — Installer (double-click to run)               ║
# ╚══════════════════════════════════════════════════════════════════════╝
# This file installs VoiceType on your Mac. It will:
#   • Install Homebrew & Python (if not already installed)
#   • Install all required packages
#   • Download the Whisper AI model (~500 MB, one time only)
#   • Set VoiceType to launch automatically at login
#   • Open the Accessibility permission screen for you

# ── Change to the folder this script lives in ──────────────────────────
cd "$(dirname "$0")"
VOICETYPE_DIR="$(pwd)"

clear
echo ""
echo "╔══════════════════════════════════════════════════════════════════╗"
echo "║                                                                  ║"
echo "║          🎙️   VoiceType — Installation Wizard   🎙️              ║"
echo "║                                                                  ║"
echo "║   Free, offline voice-to-text for Apple Silicon Macs            ║"
echo "║   Hold Right ⌥ anywhere → speak → text pastes instantly         ║"
echo "║                                                                  ║"
echo "╚══════════════════════════════════════════════════════════════════╝"
echo ""
echo "  This window will walk you through the full setup."
echo "  Total time: about 5–15 minutes (mostly model download)."
echo ""
echo "  ⚠️  Do NOT close this window during installation."
echo ""
echo "  Press Enter to begin, or Ctrl+C to cancel."
read -r

# ── 1. Check Apple Silicon ─────────────────────────────────────────────
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Step 1 of 8 — Checking your Mac"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

ARCH=$(uname -m)
if [ "$ARCH" != "arm64" ]; then
    echo "  ❌ ERROR: VoiceType requires an Apple Silicon Mac (M1/M2/M3/M4)."
    echo ""
    echo "  Your Mac uses an Intel chip, which is not supported."
    echo "  VoiceType uses Apple's MLX framework, which only runs on"
    echo "  Apple Silicon GPUs — sorry!"
    echo ""
    echo "  Press Enter to close."
    read -r
    exit 1
fi

OS_VER=$(sw_vers -productVersion | cut -d. -f1)
if [ "$OS_VER" -lt 13 ]; then
    echo "  ❌ ERROR: VoiceType requires macOS 13 (Ventura) or later."
    echo ""
    echo "  Your macOS: $(sw_vers -productVersion)"
    echo "  Please update macOS and try again."
    echo ""
    echo "  Press Enter to close."
    read -r
    exit 1
fi

echo "  ✅  Mac chip:  Apple Silicon ($ARCH)"
echo "  ✅  macOS:     $(sw_vers -productVersion)"
echo ""

# ── 2. Check disk space ────────────────────────────────────────────────
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Step 2 of 8 — Checking disk space"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

FREE_KB=$(df -k "$HOME" | awk 'NR==2 {print $4}')
FREE_GB=$(echo "scale=1; $FREE_KB / 1048576" | bc)
REQUIRED_KB=2097152  # 2 GB

if [ "$FREE_KB" -lt "$REQUIRED_KB" ]; then
    echo "  ❌ ERROR: Not enough disk space."
    echo ""
    echo "  Available:  ${FREE_GB} GB"
    echo "  Required:   ~2 GB  (AI model + packages)"
    echo ""
    echo "  Please free up space and run Install VoiceType.command again."
    echo "  Tip: Apple Menu → About This Mac → Storage → Manage"
    echo ""
    echo "  Press Enter to close."
    read -r
    exit 1
fi
echo "  ✅  Disk space: ${FREE_GB} GB available (need ~2 GB)"
echo ""

# ── 3. Check internet ─────────────────────────────────────────────────
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Step 3 of 8 — Checking internet connection"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

if ! curl -s --max-time 8 https://huggingface.co > /dev/null 2>&1; then
    echo "  ❌ ERROR: No internet connection detected."
    echo ""
    echo "  VoiceType needs internet once to download the AI model (~500 MB)."
    echo "  After that, everything works fully offline."
    echo ""
    echo "  Please connect to WiFi and try again."
    echo ""
    echo "  Press Enter to close."
    read -r
    exit 1
fi
echo "  ✅  Internet connection OK"
echo ""

# ── 4. Install Homebrew ────────────────────────────────────────────────
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Step 4 of 8 — Homebrew (Mac package manager)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

if ! command -v brew &>/dev/null && [ ! -f /opt/homebrew/bin/brew ]; then
    echo "  📦 Homebrew not found — installing now..."
    echo "     (This may ask for your Mac password — that's normal)"
    echo ""
    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
    eval "$(/opt/homebrew/bin/brew shellenv)"
    echo ""
    echo "  ✅  Homebrew installed"
else
    eval "$(/opt/homebrew/bin/brew shellenv)" 2>/dev/null || true
    echo "  ✅  Homebrew already installed ($(brew --version | head -1))"
fi
echo ""

# ── 5. Install Python 3.14 ────────────────────────────────────────────
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Step 5 of 8 — Python 3.14"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

if ! /opt/homebrew/bin/python3.14 --version &>/dev/null; then
    echo "  📦 Installing Python 3.14 (takes 1–3 minutes)..."
    brew install python@3.14
    echo ""
    echo "  ✅  Python 3.14 installed"
else
    echo "  ✅  $(/opt/homebrew/bin/python3.14 --version) already installed"
fi
echo ""

# ── 6. Create venv + install packages ────────────────────────────────
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Step 6 of 8 — Installing Python packages"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

echo "  🐍 Creating virtual environment..."
rm -rf "$VOICETYPE_DIR/venv"
/opt/homebrew/bin/python3.14 -m venv "$VOICETYPE_DIR/venv"
echo "  ✅  Virtual environment ready"
echo ""

echo "  📦 Installing packages (takes 1–3 minutes)..."
"$VOICETYPE_DIR/venv/bin/pip" install --quiet --upgrade pip
"$VOICETYPE_DIR/venv/bin/pip" install \
    mlx-whisper sounddevice numpy pyperclip pynput \
    pillow pystray pyobjc-framework-Cocoa pyobjc-framework-Quartz

echo ""

# Verify
echo "  🔍 Verifying all packages..."
"$VOICETYPE_DIR/venv/bin/python" -c "
import mlx_whisper, sounddevice, pynput, pystray, AppKit, Quartz, pyperclip, PIL
print('  ✅  All packages verified OK')
" || {
    echo ""
    echo "  ❌ Package verification failed."
    echo "     Please check the error above, then run Install VoiceType.command again."
    echo ""
    echo "  Press Enter to close."
    read -r
    exit 1
}
echo ""

# ── 7. App permissions + LaunchAgent ──────────────────────────────────
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Step 7 of 8 — Setting up auto-start at login"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

chmod +x "$VOICETYPE_DIR/VoiceType.app/Contents/MacOS/VoiceType" 2>/dev/null || true

PLIST="$HOME/Library/LaunchAgents/com.voicetype.menubar.plist"
mkdir -p "$HOME/Library/LaunchAgents"

cat > "$PLIST" << PLIST_EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.voicetype.menubar</string>
    <key>ProgramArguments</key>
    <array>
        <string>/usr/bin/open</string>
        <string>${VOICETYPE_DIR}/VoiceType.app</string>
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
PLIST_EOF

launchctl unload "$PLIST" 2>/dev/null || true
launchctl load "$PLIST"
echo "  ✅  VoiceType will auto-start when you log in"
echo ""

# ── 8. Download AI model ───────────────────────────────────────────────
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Step 8 of 8 — Downloading Whisper AI model (~500 MB)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "  ⏳ Downloading... this takes 5–10 minutes on most connections."
echo "     The model is saved to your Mac — it never downloads again."
echo "     Keep this window open!"
echo ""

"$VOICETYPE_DIR/venv/bin/python" -c "
import mlx_whisper, numpy as np, sys
try:
    mlx_whisper.transcribe(
        np.zeros(16000, dtype='float32'),
        path_or_hf_repo='mlx-community/whisper-small-mlx',
        verbose=False
    )
    print('  ✅  AI model downloaded and ready')
except OSError as e:
    if 'No space left' in str(e):
        print('')
        print('  ❌ Download failed: No space left on device.')
        print('     Free up at least 1 GB of storage and try again.')
        sys.exit(1)
    raise
" || {
    echo ""
    echo "  ❌ Model download failed — check the error above."
    echo "     Make sure you have internet access and at least 600 MB free."
    echo ""
    echo "  Press Enter to close."
    read -r
    exit 1
}
echo ""

# ── Launch the app ─────────────────────────────────────────────────────
echo "  🚀 Launching VoiceType..."
open "$VOICETYPE_DIR/VoiceType.app"
sleep 2

# ── Open Accessibility settings ────────────────────────────────────────
open "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility"

# ── Done! ──────────────────────────────────────────────────────────────
clear
echo ""
echo "╔══════════════════════════════════════════════════════════════════╗"
echo "║                                                                  ║"
echo "║            🎉  VoiceType is installed!  🎉                      ║"
echo "║                                                                  ║"
echo "╠══════════════════════════════════════════════════════════════════╣"
echo "║                                                                  ║"
echo "║  Before you can use it, grant two permissions:                   ║"
echo "║                                                                  ║"
echo "║  1. ACCESSIBILITY  (just opened for you — do this now)          ║"
echo "║     → Click the lock 🔒 to make changes                         ║"
echo "║     → Click + and find VoiceType in your folder                 ║"
echo "║     → Make sure the toggle is ON (blue)                         ║"
echo "║                                                                  ║"
echo "║  2. MICROPHONE  (prompted automatically on first recording)      ║"
echo "║     → Just click Allow when macOS asks                           ║"
echo "║                                                                  ║"
echo "╠══════════════════════════════════════════════════════════════════╣"
echo "║                                                                  ║"
echo "║  HOW TO USE:                                                     ║"
echo "║  • Look for the mic icon 🎙️ in your menu bar (top right)        ║"
echo "║  • Click it → Turn ON                                            ║"
echo "║  • Hold Right ⌥ (Option key on right side of spacebar)          ║"
echo "║  • Speak — then release ⌥ — text pastes wherever cursor is      ║"
echo "║                                                                  ║"
echo "╠══════════════════════════════════════════════════════════════════╣"
echo "║                                                                  ║"
echo "║  VoiceType will auto-start next time you log in.                 ║"
echo "║  For help: open the Dashboard from the menu bar icon.           ║"
echo "║                                                                  ║"
echo "╚══════════════════════════════════════════════════════════════════╝"
echo ""
echo "  Press Enter to close this window."
read -r
