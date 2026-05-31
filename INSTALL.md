# VoiceType — Installation & User Guide

VoiceType is a free, fully offline voice-to-text tool for Mac.  
Hold **Right ⌥** anywhere → speak → text pastes automatically. No API. No subscription. No internet needed after setup.

> ⚠️ **Requires an Apple Silicon Mac** (M1, M2, M3, or M4 chip) running macOS 13 or later.

---

## Quick Install — Double-Click Installer

**Step 1 — Move the folder somewhere permanent**

Unzip `VoiceType.zip` and move the `VoiceType` folder to a permanent location — your home folder, Documents, Desktop, wherever you like. **Don't move it after installing.**

**Step 2 — Double-click "Install VoiceType.command"**

A Terminal window opens and walks you through the full setup automatically:
- Checks your Mac (Apple Silicon, macOS version, disk space, internet)
- Installs Homebrew (if you don't have it)
- Installs Python 3.14
- Installs all required packages
- Downloads the Whisper AI model (~500 MB, one time only)
- Sets up VoiceType to auto-start every time you log in
- Launches VoiceType and opens the Accessibility permissions screen

> If macOS asks *"Are you sure you want to open this?"* — click **Open**. This is normal for `.command` files.

The whole process takes **5–15 minutes** depending on your internet speed (mostly the model download).

---

## Permissions — One-Time Setup

After the installer finishes, macOS needs two permissions before VoiceType can work.

### 1. Accessibility — Required for the hotkey to work

The installer opens this screen for you automatically.

> **System Settings → Privacy & Security → Accessibility**

1. Click the **lock 🔒** at the bottom to make changes
2. Click the **+** button
3. Navigate to your VoiceType folder and select **VoiceType.app**
4. Make sure the toggle next to it is **turned on** (blue)

### 2. Microphone — Required to record your voice

macOS will ask automatically the first time you try to record.  
Just click **Allow** when the popup appears.

---

## How to Use

Once installed, VoiceType lives in your **menu bar** (top-right of your screen). Look for the mic icon 🎙️.

| What to do | How |
|-----------|-----|
| Activate VoiceType | Click the mic icon → **Turn ON** |
| Start recording | Hold **Right ⌥** (Option key, right side of spacebar) |
| Stop & paste | Release **Right ⌥** |
| Pause (keep model loaded) | Dashboard → **Pause** or menu bar → **Turn OFF** |
| Resume instantly | Dashboard → **Resume** (no reload needed) |
| Stop completely | Dashboard → **■ Stop** |
| Open Dashboard | Click the mic icon → **Open Dashboard** |
| Quit completely | Click the mic icon → **Quit VoiceType** |

**The icon changes colour to show what's happening:**

| Colour | Meaning |
|--------|---------|
| ⚫ Dimmed icon | VoiceType is off or paused |
| 🟡 Yellow tint | Loading the AI model (wait a few seconds) |
| 🔵 Normal icon | Ready — hold Right ⌥ to speak |
| 🔴 Red tint | Recording your voice |
| 🟠 Orange tint | Transcribing speech to text |

**Tip:** Click inside a text field (message box, email, Google Doc, etc.) before speaking — the text pastes wherever your cursor is.

---

## Status HUD — Floating Pill

VoiceType shows a small floating pill near the bottom of your screen that tells you exactly what's happening at a glance — without needing to look at the menu bar.

| Dot colour | Text | Meaning |
|-----------|------|---------|
| 🟡 Yellow | Loading model… | Starting up |
| 🟢 Green | Hold ⌥ to dictate | Ready — waiting for you |
| 🔴 Red (pulsing) | Recording… | Mic is open, capturing your voice |
| 🟠 Orange | Transcribing… | Converting speech to text |
| *(hidden)* | | VoiceType is off or paused |

**Tips:**
- The pill sits just above your Dock and is always on top of other windows
- You can **drag it anywhere** on screen by clicking and dragging
- It hides automatically when you turn VoiceType off or pause it

---

## Dashboard

Click **Open Dashboard** from the menu bar icon. The dashboard has four tabs:

### 🏠 Home
- **Live status indicator** — shows exactly what VoiceType is doing right now
- **Control buttons** — Turn ON / Pause / Resume / ■ Stop
- **Stats card** — words dictated today, transcription count, average WPM, active language
- **⚡ Time Saved card** — see how much typing time you've saved in four periods:
  - **Today** — since midnight
  - **This Week** — Monday to today
  - **This Month** — 1st of month to today
  - **This Year** — Jan 1st to today
  - Data is stored on disk and survives restarts
- **Today's transcriptions** — live timestamped list of everything you've dictated today

### 📋 History
- All transcriptions grouped by date, fully scrollable

### ✦ Grammar Fix
- Paste any text and transform it instantly with one of five modes:
  - **✓ Fix Grammar** — correct spelling, capitalization, punctuation, apostrophes
  - **🎩 Formal** — professional, polished tone
  - **😊 Casual** — friendly, conversational tone
  - **✂️ Shorter** — trim to the essentials, remove filler
  - **✨ Improve** — refine phrasing and flow
- Works fully offline — no AI API, no internet needed

### ⚙️ Settings
- **Language** — switch between 12 languages; restarts the engine automatically
- **AI Model** — choose speed vs. accuracy:
  - *Whisper Small* — fastest (~3–4 sec per transcription) ✅ Default, great for everyday use
  - *Whisper Medium* — more accurate, slower (~10–15 sec)
  - *Whisper Large* — highest accuracy, slowest (~25–30 sec)
- **Auto Cleanup** — strips filler words ("um", "uh", etc.) and capitalises the first letter. Edit your custom filler word list.
- **✦ Auto Grammar Fix** — automatically fixes grammar, spelling & punctuation on every dictation before it pastes
- **Smart Noise Filter** — always active (regardless of other settings). Silently drops non-speech sounds that Whisper picks up as text — humming ("Mmmmm"), throat-clearing ("Ahmm", "Hmm"), and other repetitive noise transcriptions are discarded without pasting
- **Clear History** — wipe today's transcriptions from the Home tab

---

## Voice Commands

Say these phrases **exactly** while recording to trigger actions instead of pasting text:

| Say | Action |
|-----|--------|
| "new line" | Press Return |
| "new paragraph" | Press Return twice |
| "period" / "full stop" | Insert . |
| "comma" | Insert , |
| "question mark" | Insert ? |
| "exclamation mark" / "exclamation point" | Insert ! |
| "clear that" / "undo that" / "delete that" | Undo last paste |
| "all caps" / "caps lock" | Next dictation will be ALL CAPS |

> **Tip:** Voice commands are matched after stripping punctuation, so saying *"Question, mark."* still works.

---

## Auto Grammar Fix

When **Auto Grammar Fix** is enabled in Settings → Processing, every dictation is automatically corrected before it pastes. It fixes:

- **Capitalization** — first letter of sentences, standalone "i" → "I"
- **Missing apostrophes** — `dont` → `don't`, `cant` → `can't`, `wont` → `won't`, `im` → `I'm`, and more
- **Punctuation spacing** — removes stray spaces before commas and periods
- **Duplicate words** — removes repeated words that slip in during speech
- **a / an** — corrects `a apple` → `an apple`, `an cat` → `a cat`
- **Spelling** — uses macOS built-in spell checker to fix typos

Works completely offline. No AI API calls. If the text is already correct, it passes through unchanged.

---

## Time Saved

VoiceType tracks how many words you dictate and calculates typing time saved compared to an average typist (40 WPM). This data is stored locally at `~/.voicetype/stats.json` and persists across restarts, app updates, and reboots.

View the breakdown on the **Home** tab — the ⚡ green card shows:

| Period | What it covers |
|--------|---------------|
| **Today** | Since midnight |
| **This Week** | Monday to today |
| **This Month** | 1st of the month to today |
| **This Year** | Jan 1st to today |

---

## Language Support

VoiceType supports 12 languages. Change in **Dashboard → Settings → Language**:

English · Spanish · French · German · Hindi · Portuguese · Italian · Arabic · Japanese · Chinese · Korean · Auto-detect

Changing the language restarts the transcription engine automatically (takes a few seconds).

---

## Pause vs. Stop vs. Quit

| Action | What happens | Time to resume |
|--------|-------------|----------------|
| **Pause** | Hotkey disabled, model stays loaded in memory | ~instant |
| **■ Stop** | Worker fully killed, model unloaded from RAM | 5–10 sec reload |
| **Quit** | App exits completely | Relaunch needed |

Use **Pause** when you want a break but will be back soon — it resumes in under a second with no model reload.

---

## First Launch Notes

- The **first time you click Turn ON**, the model needs to warm up — about **5–10 seconds** (icon is yellow). After that it's fast.
- The **very first launch** after install might take up to 20 seconds — perfectly normal.
- If you switch models in Settings, the new model is loaded once, then cached for instant future starts.
- VoiceType **auto-starts on login** so the icon is always in your menu bar. Just click Turn ON when you need it.

---

## Troubleshooting

**The mic icon doesn't appear in the menu bar**
- Double-click **"Install VoiceType.command"** again — it will repair the auto-start setup
- Or log out and back in — the Launch Agent restarts it automatically

**I clicked Turn ON but it stays yellow**
- Wait up to 20 seconds on first load (model is warming up)
- If still stuck after 30 seconds, check the log:
  ```bash
  cat /tmp/vt_worker_stderr.log
  ```

**I hold Right ⌥ but nothing records**
- Make sure the Accessibility permission is ON for VoiceType (see Permissions section above)
- Try: menu bar icon → Turn OFF → Turn ON
- Or: Dashboard → ■ Stop → Turn ON

**Text pastes in the wrong place**
- Click inside a text field *before* holding Right ⌥
- Text always pastes at wherever your cursor last was

**Auto Grammar Fix doesn't seem to change anything**
- It only fixes clear mistakes — correct text passes through unchanged
- Check the toggle is ON in Dashboard → Settings → Processing

**The dashboard shows 0 words / empty history**
- Make sure VoiceType is ON (not just open) before dictating
- Stats accumulate only while the worker is running

**A Python icon appears in the Dock**
- This shouldn't happen with the current version. Fix with:
  ```bash
  pkill -f menubar.py && open ~/Documents/VoiceType/VoiceType.app
  ```
  *(Use your actual VoiceType folder path)*

**Humming or throat-clearing is pasting text**
- VoiceType has a built-in noise filter that silently drops sounds like "Hmm", "Ahmm", "Mmm" and repetitive noise transcriptions
- If a specific sound still gets through, add it to the **Filler Words** list in Settings → Auto Cleanup
- Make sure you're not holding Right ⌥ longer than needed — release as soon as you finish speaking

**Voice commands not working**
- Auto Cleanup should be OFF if you rely heavily on voice commands (Cleanup runs before command detection)
- Speak the command clearly at a normal pace

---

## Uninstall

**Easy way:** Double-click **"Uninstall VoiceType.command"** — it removes everything and guides you through the steps.

**Manual way:**
```bash
# 1. Stop auto-start
launchctl unload ~/Library/LaunchAgents/com.voicetype.menubar.plist
rm ~/Library/LaunchAgents/com.voicetype.menubar.plist

# 2. Delete saved stats and config (optional)
rm -rf ~/.voicetype

# 3. Delete the AI model cache (optional — frees 500 MB–1.5 GB)
rm -rf ~/.cache/huggingface/hub/models--mlx-community--whisper-small-mlx
rm -rf ~/.cache/huggingface/hub/models--mlx-community--whisper-medium-mlx
rm -rf ~/.cache/huggingface/hub/models--mlx-community--whisper-large-mlx

# 4. Delete the VoiceType folder
rm -rf ~/Documents/VoiceType   # or wherever you installed it
```

---

## System Requirements

| Requirement | Minimum |
|------------|---------|
| Mac chip | Apple Silicon (M1, M2, M3, or M4) |
| macOS | 13 Ventura or later |
| RAM | 8 GB |
| Disk space | ~600 MB (Small model) · ~1 GB (Medium) · ~1.5 GB (Large) |
| Internet | Only needed during initial setup |

---

## Need Help?

Check the log in Terminal — it shows exactly what's happening inside VoiceType:

```bash
cat /tmp/vt_worker_stderr.log
```
