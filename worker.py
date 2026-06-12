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

# Parakeet (NVIDIA, via parakeet-mlx) is a different engine than Whisper —
# much faster, but loaded and called through its own API.
IS_PARAKEET = "parakeet" in MODEL.lower()

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

# If the model is already downloaded, force Hugging Face into offline mode so
# loading uses the local cache and never hangs on a network round-trip to
# huggingface.co (VoiceType runs fully offline once the model is present).
# Only do this when the model is cached, so a brand-new model can still be
# fetched on first use.
def _model_is_cached(repo):
    cache = os.path.expanduser("~/.cache/huggingface/hub")
    return os.path.isdir(os.path.join(cache, "models--" + repo.replace("/", "--")))

if _model_is_cached(MODEL):
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"

import subprocess as _subprocess

# Shared text-processing (vocabulary, shortcuts, profiles, tone). Same module
# the dashboard uses, so the rules live in exactly one place.
import processing

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

# ── v1.4: vocabulary, shortcuts, per-app profiles, last-paste tracking ──────
_vocabulary    = list(_cfg.get("vocabulary", []))
_shortcuts     = dict(_cfg.get("shortcuts", {}))
_app_profiles  = dict(_cfg.get("app_profiles", {}))
_vocab_prompt  = processing.build_vocab_prompt(_vocabulary)
_last_text     = ""   # last string we pasted (for edit-by-voice)

def _reload_config():
    """Re-read vocabulary / shortcuts / profiles after the dashboard saves them."""
    global _vocabulary, _shortcuts, _app_profiles, _vocab_prompt
    cfg = _load_cfg()
    _vocabulary   = list(cfg.get("vocabulary", []))
    _shortcuts    = dict(cfg.get("shortcuts", {}))
    _app_profiles = dict(cfg.get("app_profiles", {}))
    _vocab_prompt = processing.build_vocab_prompt(_vocabulary)

def _frontmost_bundle_id():
    """Bundle id of the app the user is typing into, or None."""
    try:
        from AppKit import NSWorkspace
        app = NSWorkspace.sharedWorkspace().frontmostApplication()
        return app.bundleIdentifier() if app else None
    except Exception:
        return None

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
    # ── Edit-by-voice (operate on the last pasted text) ──
    "scratch that":       "edit_scratch",
    "delete last word":   "edit_delword",
    "delete last sentence": "edit_delsentence",
    "capitalize that":    "edit_caps",
    "make it formal":     "edit_formal",
    "make it casual":     "edit_casual",
}

# Edit commands need the last-pasted text and re-paste, so they're handled
# separately from the simple keystroke commands in _execute_cmd.
EDIT_COMMANDS = {
    "edit_scratch", "edit_delword", "edit_delsentence",
    "edit_caps", "edit_formal", "edit_casual",
}

def _press_key(key_code, shift=False, cmd=False, option=False):
    try:
        import Quartz as Q
        src = Q.CGEventSourceCreate(Q.kCGEventSourceStateHIDSystemState)
        dn  = Q.CGEventCreateKeyboardEvent(src, key_code, True)
        up  = Q.CGEventCreateKeyboardEvent(src, key_code, False)
        flags = 0
        if shift:  flags |= Q.kCGEventFlagMaskShift
        if cmd:    flags |= Q.kCGEventFlagMaskCommand
        if option: flags |= Q.kCGEventFlagMaskAlternate
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

# ── Edit-by-voice ───────────────────────────────────────────────────────────
def _backspace(n):
    """Delete n characters to the left of the cursor."""
    for _ in range(n):
        _press_key(0x33)  # 0x33 = Delete/Backspace
        time.sleep(0.004)

def _replace_last(new_text):
    """Remove the last paste and type the replacement in its place."""
    global _last_text
    if not _last_text:
        return
    _backspace(len(_last_text))
    time.sleep(0.03)
    if pyperclip:
        pyperclip.copy(new_text)
        time.sleep(0.05)
        _paste()
    _last_text = new_text

def _execute_edit(cmd):
    """Apply an edit-by-voice command to the last pasted text. No-op if nothing
    was pasted (e.g. the user clicked elsewhere first)."""
    global _last_text
    if not _last_text:
        _err("Edit command with no last text — ignoring")
        return
    if cmd == "edit_scratch":
        _backspace(len(_last_text))
        _last_text = ""
    elif cmd == "edit_delword":
        # Remove the trailing word from the cursor and from our tracked text.
        _press_key(0x33, option=True)  # Option+Backspace deletes a word
        _last_text = re.sub(r"\s*\S+\s*$", "", _last_text)
    elif cmd == "edit_delsentence":
        last = re.split(r"(?<=[.!?])\s+", _last_text.strip())
        chunk = last[-1] if last else _last_text
        _backspace(len(chunk))
        _last_text = _last_text[: len(_last_text) - len(chunk)]
    elif cmd == "edit_caps":
        _replace_last(_last_text.upper())
    elif cmd in ("edit_formal", "edit_casual"):
        mode = "formal" if cmd == "edit_formal" else "casual"
        new = processing.ai_rewrite(_last_text, mode)
        if not new:
            new = (processing.make_formal_fast(_last_text) if mode == "formal"
                   else processing.make_casual_fast(_last_text))
        _replace_last(new)

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
            elif cmd == "reload_config":
                _reload_config()
    except Exception:
        pass

# ── Audio ─────────────────────────────────────────────────────────────────
def audio_callback(indata, frames, time_info, status):
    if is_recording:
        recording_data.append(indata.copy())

def stop_and_transcribe():
    global is_recording
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

    if IS_PARAKEET:
        # Parakeet has no prompt biasing, so _vocab_prompt doesn't apply here.
        with _pk_lock:
            mel  = _pk_get_logmel(_mx.array(audio), _pk_model.preprocessor_config)
            text = _pk_model.generate(mel)[0].text.strip()
    else:
        kwargs = dict(path_or_hf_repo=MODEL, verbose=False)
        if LANGUAGE:
            kwargs["language"] = LANGUAGE
        if _vocab_prompt:
            kwargs["initial_prompt"] = _vocab_prompt  # bias toward custom words
        result = mlx_whisper.transcribe(audio, **kwargs)
        text   = result["text"].strip()

    _deliver(text, duration)

def _deliver(text, duration):
    """Post-transcription pipeline: noise filter, voice commands, shortcuts,
    per-app formatting, paste. Shared by the batch and streaming paths."""
    global _all_caps_next, _last_text

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
        elif vcmd in EDIT_COMMANDS:
            _execute_edit(vcmd)
        else:
            _execute_cmd(vcmd)
        print(f"cmd:{vcmd}", flush=True)
        print("ready", flush=True)
        return

    if _all_caps_next:
        text = text.upper()
        _all_caps_next = False

    # Expand shortcuts before formatting so expansions are styled consistently.
    text = processing.apply_shortcuts(text, _shortcuts)

    # Pick the rule for whichever app the user is typing into.
    profile = processing.get_profile(_app_profiles, _frontmost_bundle_id())

    # cleanup: per-app override of the global CLEANUP toggle.
    if profile.get("cleanup", CLEANUP):
        text = auto_cleanup(text)
    tone = profile.get("tone", "none")
    if tone == "formal":
        text = processing.make_formal_fast(text)
    elif tone == "casual":
        text = processing.make_casual_fast(text)
    if profile.get("punctuate"):
        text = processing.punctuate(text)

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
        _last_text = text
        print(f"text:{text}", flush=True)

    print("ready", flush=True)

# ── Streaming transcription (Parakeet) ─────────────────────────────────────
# Instead of transcribing the whole recording after key release, feed audio
# to the model in chunks WHILE the user is still speaking. On release only
# the last ~1s remains to process, so the felt wait is near-constant and
# small no matter how long the dictation was.
_pk_lock = threading.Lock()   # MLX model is not thread-safe across sessions
_session = None

_FEED_INTERVAL = 1.0                      # seconds between feeds while speaking
_FEED_MIN      = int(0.5 * SAMPLE_RATE)   # don't feed scraps smaller than this

class _StreamSession(threading.Thread):
    """One recording's streaming transcription. All MLX streaming ops happen
    on this single thread (incremental state must not hop threads)."""

    def __init__(self, buf):
        super().__init__(daemon=True)
        self.buf      = buf            # the recording_data list of THIS recording
        self.stop_evt = threading.Event()
        self.duration = 0.0            # set by on_release before stop_evt
        self.start()

    def finish(self, duration):
        self.duration = duration
        self.stop_evt.set()

    def run(self):
        try:
            self._stream()
        except Exception:
            _err("Streaming failed — falling back to batch:", traceback.format_exc())
            try:
                self._batch_fallback()
            except Exception:
                _err("Batch fallback FAILED:", traceback.format_exc())
                print("ready", flush=True)

    def _total_samples(self):
        return sum(len(c) for c in self.buf)

    def _stream(self):
        idx, fed, feeds = 0, 0, 0
        t_feeding = 0.0
        # depth=1: benchmarked 0.73s compute per 1s of speech (keeps up in real
        # time); depth=2 took 1.14s per 1s and falls behind while speaking.
        with _pk_model.transcribe_stream(context_size=(256, 256), depth=1) as stream:
            while not self.stop_evt.wait(_FEED_INTERVAL):
                chunks = self.buf[idx:]
                if sum(len(c) for c in chunks) < _FEED_MIN:
                    continue
                idx += len(chunks)
                t0 = time.time()
                with _pk_lock:
                    stream.add_audio(_mx.array(np.concatenate(chunks).flatten()))
                t_feeding += time.time() - t0
                fed += sum(len(c) for c in chunks)
                feeds += 1

            # key released — drop too-short recordings (matches batch path)
            if self._total_samples() < SAMPLE_RATE * 0.3:
                print("ready", flush=True)
                return

            t0 = time.time()
            chunks = self.buf[idx:]
            with _pk_lock:
                if chunks:
                    stream.add_audio(_mx.array(np.concatenate(chunks).flatten()))
                text = stream.result.text.strip()
            tail = time.time() - t0

        _err(f"Streaming: {feeds} feeds ({t_feeding:.2f}s) while speaking, "
             f"tail wait {tail:.2f}s for {self._total_samples()/SAMPLE_RATE:.1f}s audio")
        _deliver(text, self.duration)

    def _batch_fallback(self):
        audio = np.concatenate(self.buf, axis=0).flatten() if self.buf else np.zeros(0)
        if len(audio) < SAMPLE_RATE * 0.3:
            print("ready", flush=True)
            return
        with _pk_lock:
            mel  = _pk_get_logmel(_mx.array(audio), _pk_model.preprocessor_config)
            text = _pk_model.generate(mel)[0].text.strip()
        _deliver(text, self.duration)

def on_press(key):
    global is_recording, recording_data, record_start_time, _session
    if _paused.is_set():
        return
    if key == RECORD_KEY and not is_recording:
        is_recording      = True
        recording_data    = []
        record_start_time = time.time()
        print("recording", flush=True)
        if IS_PARAKEET:
            try:
                _session = _StreamSession(recording_data)
            except Exception:
                _err("Could not start stream session:", traceback.format_exc())
                _session = None   # on_release falls back to batch

def _safe_transcribe():
    """Run a transcription; on ANY failure, log it and report ready so the
    menubar never sticks on 'transcribing'."""
    try:
        stop_and_transcribe()
    except Exception:
        _err("Transcription FAILED:", traceback.format_exc())
        print("ready", flush=True)

def on_release(key):
    global is_recording, _session
    if key == RECORD_KEY and is_recording:
        if IS_PARAKEET and _session is not None:
            is_recording = False
            print("transcribing", flush=True)
            _session.finish(time.time() - (record_start_time or time.time()))
            _session = None
        else:
            threading.Thread(target=_safe_transcribe, daemon=True).start()

# ── Load model ────────────────────────────────────────────────────────────
if not IS_PARAKEET and mlx_whisper is None:
    _err("Cannot start — mlx_whisper failed to import.")
    sys.exit(1)

try:
    print("loading", flush=True)
    _err("Loading model...")
    if IS_PARAKEET:
        import mlx.core as _mx
        from parakeet_mlx import from_pretrained as _pk_from_pretrained
        from parakeet_mlx.audio import get_logmel as _pk_get_logmel
        _pk_model = _pk_from_pretrained(MODEL)
        # Force-evaluate every weight NOW, in this thread. MLX loads weights
        # lazily, and a lazy array first evaluated from another thread crashes
        # with "There is no Stream(gpu, 0) in current thread" — which is
        # exactly what transcription threads would hit on the decoder's
        # embedding (silence warmup never touches it).
        from mlx.utils import tree_flatten as _tree_flatten
        _mx.eval([v for _, v in _tree_flatten(_pk_model.parameters())])
        # Warm up so the first real dictation doesn't pay MLX compile time.
        _pk_model.generate(_pk_get_logmel(
            _mx.array(np.zeros(SAMPLE_RATE, dtype=np.float32)),
            _pk_model.preprocessor_config))
        # Warm up the streaming path too — its kernels compile separately,
        # and the first-ever add_audio once hit a Metal alloc underflow in
        # the library (seen 2026-06-12). Absorb both here, not on the
        # user's first dictation. Non-fatal: streaming falls back to batch.
        try:
            with _pk_model.transcribe_stream(context_size=(256, 256), depth=1) as _ws:
                _ws.add_audio(_mx.array(np.zeros(SAMPLE_RATE, dtype=np.float32)))
                _ws.add_audio(_mx.array(np.zeros(SAMPLE_RATE // 2, dtype=np.float32)))
                _ = _ws.result.text
            del _ws
        except Exception:
            _err("Streaming warmup failed (non-fatal):", traceback.format_exc())
    else:
        kwargs = dict(path_or_hf_repo=MODEL, verbose=False)
        if LANGUAGE:
            kwargs["language"] = LANGUAGE
        mlx_whisper.transcribe(np.zeros(SAMPLE_RATE, dtype=np.float32), **kwargs)
    _err("Model ready")
    print("ready", flush=True)
except Exception:
    _err("Model load FAILED:", traceback.format_exc())
    sys.exit(1)

def _open_stream():
    s = sd.InputStream(
        samplerate=SAMPLE_RATE, channels=1,
        dtype="float32", callback=audio_callback
    )
    s.start()
    return s

def _start_stream_with_recovery():
    """Open the mic stream, self-healing the macOS CoreAudio input wedge.

    PaErrorCode -9986 ("Audio Hardware Not Running") means the system-wide
    CoreAudio *input* path is stuck: output keeps working but every input
    client fails, often after a Continuity iPhone-mic glitch. Permissions
    and our code are fine — only restarting coreaudiod clears it. So after
    plain retries we ask the user (admin prompt) to restart coreaudiod,
    then retry once more.
    """
    last_exc = None
    for attempt in range(3):
        try:
            return _open_stream()
        except sd.PortAudioError as e:
            last_exc = e
            _err(f"Audio stream attempt {attempt + 1} failed: {e}")
            time.sleep(1 + attempt)
    if "-9986" in str(last_exc):
        _err("CoreAudio input wedged (-9986) — asking user to restart coreaudiod")
        rc = _subprocess.run(
            ["osascript", "-e",
             'do shell script "killall coreaudiod" '
             'with prompt "VoiceType: the macOS microphone system (coreaudiod) '
             'is stuck and needs a restart to fix dictation." '
             'with administrator privileges'],
            capture_output=True).returncode
        if rc == 0:
            time.sleep(3)
            for attempt in range(3):
                try:
                    return _open_stream()
                except sd.PortAudioError as e:
                    last_exc = e
                    time.sleep(1 + attempt)
        else:
            _err("User declined (or osascript failed) — coreaudiod not restarted")
    raise last_exc

try:
    stream = _start_stream_with_recovery()
    _err("Audio stream started")
except Exception:
    _err("Audio stream FAILED:", traceback.format_exc())
    _subprocess.run(
        ["osascript", "-e",
         'display notification "Microphone could not be started — '
         'run: sudo killall coreaudiod  (details in /tmp/voicetype_worker.log)" '
         'with title "VoiceType"'],
        capture_output=True)
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
