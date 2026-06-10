# VoiceType v1.4 — Custom Vocabulary, Per-App Profiles, Edit-by-Voice

## Goal
Three features that make dictation more accurate and hands-free:
1. **Custom Vocabulary** — recognition tuning + text shortcuts
2. **Per-App Profiles** — auto-adjust formatting/tone per focused app
3. **Edit-by-Voice** — correct the last dictation with a spoken phrase

## Architecture

### New shared module: `processing.py`
Single source of truth for text transforms used by both `worker.py` (at paste time)
and `dashboard.py` (grammar page). Contains:
- `load_config()` — read `~/.voicetype/config.json`
- `build_vocab_prompt(words)` — turn custom words into a Whisper `initial_prompt`
- `apply_shortcuts(text, shortcuts)` — whole-phrase, case-insensitive expansion
- Ollama helpers (`ollama_find_model`, `ollama_call`, `OLLAMA_PROMPTS`) + `ai_rewrite(text, mode)`
- `make_formal_fast` / `make_casual_fast` — fast rule-based tone (no network latency)
- `punctuate(text)` — capitalize + ensure terminal punctuation
- `DEFAULT_PROFILES`, `get_profile(profiles, bundle_id)`, `apply_profile(text, profile)`

`dashboard.py` imports the Ollama helpers from `processing.py` (removing its duplicate).
Its rich rule-based `_make_formal/_make_casual` (used only by the manual grammar page)
stay in place.

## Config schema (`~/.voicetype/config.json`)
```json
{
  "filler_words": ["uh", "hmm", ...],
  "vocabulary": ["Kashish", "VoiceType", "Higgsfield"],
  "shortcuts": { "my email": "kaggarwal852@gmail.com", "sig": "Best, Kashish" },
  "app_profiles": {
    "default":                     { "cleanup": true,  "punctuate": false, "tone": "none" },
    "com.apple.mail":              { "cleanup": true,  "punctuate": true,  "tone": "formal" },
    "com.tinyspeck.slackmacgap":   { "cleanup": true,  "punctuate": false, "tone": "casual" },
    "net.whatsapp.WhatsApp":       { "cleanup": true,  "punctuate": false, "tone": "casual" },
    "com.microsoft.VSCode":        { "cleanup": false, "punctuate": false, "tone": "none" }
  }
}
```

## Feature 1 — Custom Vocabulary
- **Recognition:** `build_vocab_prompt(vocabulary)` → passed as `initial_prompt` to
  `mlx_whisper.transcribe` in `worker.py`. Biases Whisper toward the user's words.
- **Shortcuts:** after transcription, `apply_shortcuts` replaces trigger phrases.
  Applied before tone/punctuation so expansions are formatted consistently.
- **UI:** two new Settings sections (chips list like filler words) — add/remove words;
  add/remove `trigger → expansion` pairs.

## Feature 2 — Per-App Profiles
- `worker.py` detects the frontmost app via `AppKit.NSWorkspace.sharedWorkspace()
  .frontmostApplication().bundleIdentifier()` at paste time.
- `get_profile` picks the app's rule, else `default`.
- `apply_profile` applies, in order: cleanup (filler removal) → tone (fast rule-based,
  to keep paste instant) → punctuate.
- **UI:** Settings section listing app rules; each row = app name + cleanup toggle +
  punctuate toggle + tone dropdown (none/formal/casual). Add-app and remove-row.
- Ships with `DEFAULT_PROFILES` seeded into config on first run if absent.

## Feature 3 — Edit-by-Voice
New entries in `VOICE_COMMANDS` operating on `_last_text` (the last pasted string),
only valid immediately after a paste (cursor still at end). If `_last_text` is empty → no-op.
- `scratch that` → Cmd+Z (undo the paste) — reliable, reuses existing undo.
- `delete last word` → Option+Backspace; trim `_last_text`'s last word.
- `delete last sentence` → backspace the char-length of the last sentence in `_last_text`.
- `capitalize that` → `replace_last(_last_text.upper())`.
- `make it formal` → `replace_last(ai_rewrite(t,"formal") or make_formal_fast(t))`.
- `make it casual` → `replace_last(ai_rewrite(t,"casual") or make_casual_fast(t))`.

`replace_last(new)`: backspace `len(_last_text)` chars, paste `new`, set `_last_text = new`.

**Limitation (documented):** works only while the cursor is still where the text landed.
Clicking elsewhere first makes these a no-op (safer than deleting wrong text).

## Testing
- Unit-level: `processing.py` functions tested directly (vocab prompt, shortcuts,
  profile selection, fast tone, punctuate) via a quick Python harness.
- Integration: one clean app restart; verify dictation still works, vocabulary biases
  recognition, a shortcut expands, an app profile changes formatting, and each
  edit-by-voice phrase behaves. No rapid restarts (known model-load gotcha).

## Out of scope (YAGNI)
- Syncing config across machines, regex shortcuts, multi-step macros, per-app
  vocabulary, GUI for reordering rules.
