#!/usr/bin/env python3
"""
VoiceType Worker — handles all recording, transcription, and pasting.
Prints status lines to stdout so menubar.py can update the icon and dashboard.

Stdout protocol:
  loading          → warming up model
  ready            → hotkey active
  paused           → hotkey disabled (pause mode)
  recording        → mic open
  transcribing     → processing audio
  wpm:<int>        → words per minute for last recording
  text:<string>    → finished transcription (dashboard shows it)
  cmd:<name>       → voice command executed (feedback only)
"""

import threading
import time
import sys
import os
import re
import json
import traceback

# ── Args ──────────────────────────────────────────────────────────────────
LANGUAGE = "en"
CLEANUP  = False
MODEL    = "mlx-community/whisper-small-mlx"

i = 1
while i < len(sys.argv):
    if sys.argv[i] == "--lang" and i + 1 < len(sys.argv):
        LANGUAGE = sys.argv[i + 1] or None
        i += 2
    elif sys.argv[i] == "--cleanup":
        CLEANUP = True
        i += 1
    elif sys.argv[i] == "--model" and i + 1 < len(sys.argv):
        MODEL = sys.argv[i + 1]
        i += 2
    else:
        i += 1

# Log errors to file
_log = open("/tmp/voicetype_worker.log", "w", buffering=1)
def _err(*args):
    print(*args, file=_log, flush=True)
    print(*args, file=sys.stderr, flush=True)

_err(f"Language: {LANGUAGE!r}  Cleanup: {CLEANUP}  Model: {MODEL}")

CONFIG_PATH = os.path.expanduser("~/.voicetype/config.json")

def _load_cfg():
    try:
        with open(CONFIG_PATH) as f:
            return json.load(f)
    except Exception:
        return {}

_cfg = _load_cfg()

import subprocess as _subprocess

try:
    import mlx_whisper
except Exception:
    _err("mlx_whisper FAILED:", traceback.format_exc())
    mlx_whisper = None

try:
    import numpy as np
except Exception as e:
    _err("numpy FAILED:", e)
    sys.exit(1)

try:
    import Quartz
    def _paste():
        import Quartz as Q
        src  = Q.CGEventSourceCreate(Q.kCGEventSourceStateHIDSystemState)
        v_dn = Q.CGEventCreateKeyboardEvent(src, 0x09, True)
        v_up = Q.CGEventCreateKeyboardEvent(src, 0x09, False)
        Q.CGEventSetFlags(v_dn, Q.kCGEventFlagMaskCommand)
        Q.CGEventSetFlags(v_up, Q.kCGEventFlagMaskCommand)
        Q.CGEventPost(Q.kCGHIDEventTap, v_dn)
        Q.CGEventPost(Q.kCGHIDEventTap, v_up)
except Exception:
    def _paste():
        _subprocess.run([
            "osascript", "-e",
            'tell application "System Events" to keystroke "v" using command down'
        ])

try:
    import pyperclip
except Exception:
    _err("pyperclip FAILED")
    pyperclip = None

try:
    import sounddevice as sd
except Exception:
    _err("sounddevice FAILED:", traceback.format_exc())
    sys.exit(1)

try:
    from pynput import keyboard
except Exception:
    _err("pynput FAILED:", traceback.format_exc())
    sys.exit(1)

RECORD_KEY  = keyboard.Key.alt_r
SAMPLE_RATE = 16000

is_recording      = False
recording_data    = []
record_start_time = None

_paused        = threading.Event()
_all_caps_next = False

# ── Filler words ──────────────────────────────────────────────────────────
_filler_words = list(_cfg.get("filler_words", ["um", "uh", "hmm", "hm", "er"]))

# Sounds that get a trailing + (match repeated chars: hmm, hmmm, hmmmmm)
_SOUNDS = {"um", "uh", "hmm", "hm", "er", "mm", "ah", "ahh", "mmm"}

def _build_filler_re(words):
    if not words:
        return None
    parts = []
    for w in words:
        e = re.escape(w)
        if w.lower() in _SOUNDS:
            e += "+"
        parts.append(e)
    return re.compile(r"\b(" + "|".join(parts) + r")\b[,.]?\s*", re.IGNORECASE)

_FILLER_RE = _build_filler_re(_filler_words)

# ── Noise / non-speech detection ──────────────────────────────────────────

# Matches an ENTIRE transcription that is just humming/filler sounds.
# Catches: "Mmm", "Mmmm", "Ahmm", "Ahm", "Hm.", "Uh hm", "Mm hmm" etc.
_NOISE_TEXT_RE = re.compile(
    r"^[\s,.]*((?:m+h?|h+m*|a+h*m*|u+h*m*|e+r*|oh*)[\s,.]*)+$",
    re.IGNORECASE
)

def _is_noise(text):
    """Return True if the whole transcription is non-speech sound to skip."""
    t = text.strip()
    if not t:
        return True
    # Repetitive single letter: "Mmmmmm", "Aaaaaaa"
    letters = re.sub(r"[^a-zA-Z]", "", t)
    if letters and len(set(letters.lower())) == 1 and len(letters) > 2:
        return True
    # Dominant single letter (>85%): catches "Mmmm." with trailing punct
    if len(letters) >= 4:
        top = max(set(letters.lower()), key=letters.lower().count)
        if letters.lower().count(top) / len(letters) >= 0.85:
            return True
    # Entire text matches humming/filler sound pattern
    if _NOISE_TEXT_RE.match(t):
        return True
    return False

# ── Voice commands ────────────────────────────────────────────────────────
VOICE_COMMANDS = {
    "new line":          "newline",
    "new paragraph":     "newparagraph",
    "period":            "period",
    "full stop":         "period",
    "comma":             "comma",
    "question mark":     "question",
    "exclamation mark":  "exclamation",
    "exclamation point": "exclamation",
    "clear that":        "undo",
    "undo that":         "undo",
    "delete that":       "undo",
    "all caps":          "allcaps",
    "caps lock":         "allcaps",
}

def _press_key(key_code, shift=False, cmd=False):
    try:
        import Quartz as Q
        src = Q.CGEventSourceCreate(Q.kCGEventSourceStateHIDSystemState)
        dn  = Q.CGEventCreateKeyboardEvent(src, key_code, True)
        up  = Q.CGEventCreateKeyboardEvent(src, key_code, False)
        flags = 0
        if shift: flags |= Q.kCGEventFlagMaskShift
        if cmd:   flags |= Q.kCGEventFlagMaskCommand
        if flags:
            Q.CGEventSetFlags(dn, flags)
            Q.CGEventSetFlags(up, flags)
        Q.CGEventPost(Q.kCGHIDEventTap, dn)
        time.sleep(0.02)
        Q.CGEventPost(Q.kCGHIDEventTap, up)
    except Exception as exc:
        _err(f"_press_key failed: {exc}")

def _execute_cmd(cmd):
    if cmd == "newline":
        _press_key(0x24)
    elif cmd == "newparagraph":
        _press_key(0x24)
        time.sleep(0.05)
        _press_key(0x24)
    elif cmd == "period":
        _press_key(0x2F)
    elif cmd == "comma":
        _press_key(0x2B)
    elif cmd == "question":
        _press_key(0x2C, shift=True)
    elif cmd == "exclamation":
        _press_key(0x12, shift=True)
    elif cmd == "undo":
        _press_key(0x06, cmd=True)

def auto_cleanup(text):
    if _FILLER_RE:
        text = _FILLER_RE.sub("", text)
    text = re.sub(r"  +", " ", text)
    text = re.sub(r"\s+([.,!?;:])", r"\1", text)
    text = text.strip()
    if text:
        text = text[0].upper() + text[1:]
    return text

# ── Stdin listener ────────────────────────────────────────────────────────
def _stdin_listener():
    global _filler_words, _FILLER_RE, _all_caps_next
    try:
        for raw in sys.stdin:
            cmd = raw.strip()
            if cmd == "pause":
                _paused.set()
                print("paused", flush=True)
            elif cmd == "resume":
                _paused.clear()
                print("ready", flush=True)
            elif cmd.startswith("filler:"):
                words_str = cmd[7:]
                _filler_words = [w.strip() for w in words_str.split(",") if w.strip()]
                _FILLER_RE = _build_filler_re(_filler_words)
    except Exception:
        pass

# ── Audio ─────────────────────────────────────────────────────────────────
def audio_callback(indata, frames, time_info, status):
    if is_recording:
        recording_data.append(indata.copy())

def stop_and_transcribe():
    global is_recording, _all_caps_next
    is_recording = False
    duration = time.time() - (record_start_time or time.time())

    if not recording_data:
        print("ready", flush=True)
        return

    audio = np.concatenate(recording_data, axis=0).flatten()
    if len(audio) < SAMPLE_RATE * 0.3:
        print("ready", flush=True)
        return

    print("transcribing", flush=True)

    kwargs = dict(path_or_hf_repo=MODEL, verbose=False)
    if LANGUAGE:
        kwargs["language"] = LANGUAGE

    result = mlx_whisper.transcribe(audio, **kwargs)
    text   = result["text"].strip()

    if not text or _is_noise(text):
        _err(f"Skipped (noise/empty): {text!r}")
        print("ready", flush=True)
        return

    normalized = re.sub(r"[^\w\s]", "", text.lower()).strip()
    normalized = re.sub(r"\s+", " ", normalized)
    if normalized in VOICE_COMMANDS:
        vcmd = VOICE_COMMANDS[normalized]
        _err(f"Voice command: {text!r} → {vcmd}")
        if vcmd == "allcaps":
            _all_caps_next = True
        else:
            _execute_cmd(vcmd)
        print(f"cmd:{vcmd}", flush=True)
        print("ready", flush=True)
        return

    if _all_caps_next:
        text = text.upper()
        _all_caps_next = False

    if CLEANUP:
        text = auto_cleanup(text)

    if text:
        _err(f"Transcribed: {text!r}")

        word_count = len(text.split())
        if duration > 0.5 and word_count > 0:
            wpm = int((word_count / duration) * 60)
            print(f"wpm:{wpm}", flush=True)

        if pyperclip:
            pyperclip.copy(text)
        time.sleep(0.1)
        _paste()
        print(f"text:{text}", flush=True)

    print("ready", flush=True)

def on_press(key):
    global is_recording, recording_data, record_start_time
    if _paused.is_set():
        return
    if key == RECORD_KEY and not is_recording:
        is_recording      = True
        recording_data    = []
        record_start_time = time.time()
        print("recording", flush=True)

def on_release(key):
    if key == RECORD_KEY and is_recording:
        threading.Thread(target=stop_and_transcribe, daemon=True).start()

# ── Load model ────────────────────────────────────────────────────────────
if mlx_whisper is None:
    _err("Cannot start — mlx_whisper failed to import.")
    sys.exit(1)

try:
    print("loading", flush=True)
    _err("Loading model...")
    kwargs = dict(path_or_hf_repo=MODEL, verbose=False)
    if LANGUAGE:
        kwargs["language"] = LANGUAGE
    mlx_whisper.transcribe(np.zeros(SAMPLE_RATE, dtype=np.float32), **kwargs)
    _err("Model ready")
    print("ready", flush=True)
except Exception:
    _err("Model load FAILED:", traceback.format_exc())
    sys.exit(1)

try:
    stream = sd.InputStream(
        samplerate=SAMPLE_RATE, channels=1,
        dtype="float32", callback=audio_callback
    )
    stream.start()
    _err("Audio stream started")
except Exception:
    _err("Audio stream FAILED:", traceback.format_exc())
    sys.exit(1)

threading.Thread(target=_stdin_listener, daemon=True).start()
_err("Stdin listener started")

try:
    _err("Starting keyboard listener...")
    with keyboard.Listener(on_press=on_press, on_release=on_release) as listener:
        _err("Keyboard listener running")
        listener.join()
except Exception:
    _err("Keyboard listener FAILED:", traceback.format_exc())
