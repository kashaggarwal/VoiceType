# 🎙️ VoiceType

**Free, fully offline voice-to-text for Mac.**  
Hold **Right ⌥** anywhere → speak → text pastes automatically.  
No API key. No subscription. No internet needed after setup.

> ⚠️ **Requires Apple Silicon** (M1, M2, M3, or M4) · macOS 13 Ventura or later

---

## Why VoiceType?

Most voice-to-text tools send your audio to a cloud server. VoiceType runs entirely on your Mac using [OpenAI Whisper](https://github.com/openai/whisper) — your voice never leaves your machine.

| | VoiceType | Cloud tools |
|--|-----------|-------------|
| Works offline | ✅ Always | ❌ Never |
| Sends audio to servers | ❌ Never | ✅ Always |
| Monthly fee | ❌ Free | 💸 Usually |
| Works in any app | ✅ Yes | Depends |
| Grammar fix (offline) | ✅ Built-in | Usually cloud |

---

## Features

- **Hold-to-dictate** — hold Right ⌥ anywhere (any app, any text field), speak, release. Done.
- **Floating status pill** — a tiny HUD near your Dock shows exactly what's happening at a glance
- **Auto Grammar Fix** — corrects capitalization, apostrophes, punctuation and duplicate words before pasting — fully offline
- **Voice commands** — say *"new line"*, *"comma"*, *"clear that"* and more while recording
- **Smart Noise Filter** — silently drops throat-clearing, humming, and non-speech sounds
- **Dashboard** with 4 tabs:
  - 🏠 **Home** — live status, controls, today's stats, ⚡ Time Saved tracker
  - 📋 **History** — all transcriptions grouped by date
  - ✦ **Grammar Fix** — paste any text and rewrite it in 5 modes (Fix, Formal, Casual, Shorter, Improve)
  - ⚙️ **Settings** — language, AI model, cleanup options
- **12 languages** — English, Spanish, French, German, Hindi, Portuguese, Italian, Arabic, Japanese, Chinese, Korean, Auto-detect
- **3 Whisper models** — Small (fast, ~3s), Medium (~10s), Large (most accurate, ~25s)
- **Auto-starts on login** — always in your menu bar, ready when you are

---

## Install

### 1 — Download

Download the latest release → **[Releases →](https://github.com/kashaggarwal/VoiceType/releases)**

Unzip `VoiceType.zip` and move the `VoiceType` folder to a permanent location (Documents, home folder, Desktop — your choice). **Don't move it after installing.**

### 2 — Run the installer

Double-click **`Install VoiceType.command`**

A Terminal window opens and handles everything automatically:

- Checks your Mac (chip, macOS version, disk space)
- Installs Homebrew (if not already installed)
- Installs Python 3.14
- Installs all required packages
- Downloads the Whisper AI model (~500 MB, one time only)
- Sets up auto-start on login
- Opens the Accessibility permissions screen

> If macOS asks *"Are you sure you want to open this?"* — click **Open**. Normal for `.command` files.

Total time: **5–15 minutes** (mostly the model download).

### 3 — Grant permissions

**Accessibility** (required for the hotkey):
> System Settings → Privacy & Security → Accessibility → click 🔒 → **+** → select `VoiceType.app` → toggle ON

**Microphone** (required to record):
> macOS asks automatically on first use — click **Allow**

---

## How to use

Once installed, VoiceType lives in your **menu bar** 🎙️

1. Click the mic icon → **Turn ON**
2. Click inside any text field (message, doc, email, search bar...)
3. Hold **Right ⌥** and speak
4. Release **Right ⌥** — text pastes instantly

**Icon colours at a glance:**

| Colour | Status |
|--------|--------|
| ⚫ Dimmed | Off or paused |
| 🟡 Yellow | Loading AI model (few seconds) |
| 🔵 Normal | Ready — hold Right ⌥ to speak |
| 🔴 Red | Recording |
| 🟠 Orange | Transcribing |

---

## Voice commands

Say these **while recording** to trigger actions instead of pasting text:

| Say | Does |
|-----|------|
| `"new line"` | Press Return |
| `"new paragraph"` | Press Return twice |
| `"period"` / `"full stop"` | Insert `.` |
| `"comma"` | Insert `,` |
| `"question mark"` | Insert `?` |
| `"exclamation mark"` | Insert `!` |
| `"clear that"` / `"undo that"` | Undo last paste |
| `"all caps"` | Next dictation in ALL CAPS |

---

## Pause vs Stop vs Quit

| Action | Effect | Resume time |
|--------|--------|------------|
| **Pause** | Hotkey off, model stays in RAM | ~instant |
| **■ Stop** | Worker killed, model unloaded | 5–10 sec |
| **Quit** | App exits | Relaunch needed |

Use **Pause** when you want a short break — it comes back instantly with no reload.

---

## System requirements

| | Minimum |
|--|---------|
| Chip | Apple Silicon (M1 / M2 / M3 / M4) |
| macOS | 13 Ventura or later |
| RAM | 8 GB |
| Disk | ~600 MB (Small) · ~1 GB (Medium) · ~1.5 GB (Large) |
| Internet | Only during first install |

---

## Uninstall

**Easy:** Double-click **`Uninstall VoiceType.command`**

**Manual:**
```bash
launchctl unload ~/Library/LaunchAgents/com.voicetype.menubar.plist
rm ~/Library/LaunchAgents/com.voicetype.menubar.plist
rm -rf ~/.voicetype
# Optional — delete cached AI models (frees up to 1.5 GB):
rm -rf ~/.cache/huggingface/hub/models--mlx-community--whisper-*
# Then delete the VoiceType folder itself
```

---

## Troubleshooting

**Mic icon doesn't appear in menu bar**
→ Double-click `Install VoiceType.command` again to repair auto-start, or log out and back in.

**Stuck on yellow / loading forever**
→ Wait up to 20 seconds on first load. If still stuck: `cat /tmp/vt_worker_stderr.log`

**Right ⌥ does nothing**
→ Check Accessibility permission is ON for VoiceType. Try: menu bar → Turn OFF → Turn ON.

**Text pastes in wrong place**
→ Click inside the text field *before* holding Right ⌥.

**Throat-clearing is pasting text**
→ The Smart Noise Filter handles most cases automatically. For anything that slips through, add it to Settings → Auto Cleanup → Filler Words.

---

## License

MIT — see [LICENSE](LICENSE)

---

*Built for Mac. Runs on your machine. Stays on your machine.* 🎙️
