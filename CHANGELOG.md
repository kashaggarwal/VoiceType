# Changelog

## v1.5

**Faster dictation — streaming transcription.** Speech is now transcribed
*while you talk* instead of only after you release the key. The wait after you
finish is now well under a second, and stays roughly constant no matter how
long you spoke (long paragraphs used to take 8–10 seconds; now ~0.5–1s).
Applies to the Parakeet model, with automatic fallback to the old method if
anything goes wrong mid-dictation.

- **New Parakeet speech model** — the fastest engine, selectable from the AI
  Model dropdown in the dashboard ("Parakeet — fastest ⚡", English + EU
  languages). Whisper models remain available for other languages.
- **Settings persist across launches** — your language and model choices are
  saved and restored on restart (previously they reset every launch).
- **Microphone self-heal** — if macOS's audio system gets stuck (a system-level
  glitch that broke dictation entirely), the app now retries, offers a one-click
  fix, and explains the problem instead of failing silently.
- **More robust transcription** — any transcription error now recovers cleanly;
  the menu-bar icon can no longer get stuck on "transcribing".

## v1.4

Custom vocabulary, voice shortcuts (text expansion), per-app formatting
profiles, edit-by-voice commands (scratch that, make it formal/casual, delete
last word/sentence), live settings reload, shared text-processing module, and a
33-test unit suite.

## v1.3

By-month time-saved strip, full-page scroll, offline model loading, dynamic
version.

## v1.2

HUD overlay, AI grammar fix, noise detection.
