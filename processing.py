"""
Shared text-processing for VoiceType.

Imported by both worker.py (applied at paste time) and dashboard.py, so the
rules live in exactly one place. Pure functions only — no app/UI state.
"""

import json
import os
import re
import urllib.request

CONFIG_PATH = os.path.expanduser("~/.voicetype/config.json")


def load_config():
    try:
        with open(CONFIG_PATH) as f:
            return json.load(f)
    except Exception:
        return {}


# ── Custom vocabulary ──────────────────────────────────────────────────────
def build_vocab_prompt(words):
    """Turn the user's custom words into a Whisper initial_prompt that biases
    recognition toward them. Returns None when there are no words."""
    words = [w.strip() for w in (words or []) if w and w.strip()]
    if not words:
        return None
    return "Vocabulary: " + ", ".join(words) + "."


# ── Shortcuts (text expansion) ─────────────────────────────────────────────
def apply_shortcuts(text, shortcuts):
    """Replace whole-phrase triggers with their expansion (case-insensitive).
    Longer triggers are matched first so 'my email address' wins over 'my email'."""
    if not shortcuts or not text:
        return text
    for trigger in sorted(shortcuts, key=len, reverse=True):
        expansion = shortcuts[trigger]
        if not trigger.strip():
            continue
        t = trigger.strip()
        # \b only works against word characters — a trigger edged with
        # punctuation (e.g. "c++") needs a whitespace boundary instead.
        left = r"\b" if t[0].isalnum() else r"(?<!\S)"
        right = r"\b" if t[-1].isalnum() else r"(?!\S)"
        pattern = left + re.escape(t) + right
        text = re.sub(pattern, lambda m, e=expansion: e, text, flags=re.IGNORECASE)
    return text


# ── Punctuation / capitalization ───────────────────────────────────────────
def punctuate(text):
    """Capitalize the first letter and ensure the text ends with . ! or ?"""
    text = (text or "").strip()
    if not text:
        return text
    text = text[0].upper() + text[1:]
    if text[-1] not in ".!?":
        text += "."
    return text


# ── Fast rule-based tone (no network latency, for per-app profiles) ─────────
_EXPAND = [
    (r"\bdon't\b", "do not"), (r"\bcan't\b", "cannot"), (r"\bwon't\b", "will not"),
    (r"\bisn't\b", "is not"), (r"\baren't\b", "are not"), (r"\bwasn't\b", "was not"),
    (r"\bweren't\b", "were not"), (r"\bhasn't\b", "has not"), (r"\bhaven't\b", "have not"),
    (r"\bhadn't\b", "had not"), (r"\bdidn't\b", "did not"), (r"\bdoesn't\b", "does not"),
    (r"\bshouldn't\b", "should not"), (r"\bwouldn't\b", "would not"),
    (r"\bcouldn't\b", "could not"), (r"\bI'm\b", "I am"), (r"\bI've\b", "I have"),
    (r"\bI'll\b", "I will"), (r"\bit's\b", "it is"), (r"\bthat's\b", "that is"),
    (r"\bthere's\b", "there is"), (r"\bthey're\b", "they are"), (r"\bwe're\b", "we are"),
    (r"\byou're\b", "you are"), (r"\blet's\b", "let us"), (r"\bwanna\b", "want to"),
    (r"\bgonna\b", "going to"), (r"\bgotta\b", "have to"), (r"\byeah\b", "yes"),
    (r"\bnope\b", "no"),
]
_CONTRACT = [
    (r"\bdo not\b", "don't"), (r"\bcannot\b", "can't"), (r"\bwill not\b", "won't"),
    (r"\bis not\b", "isn't"), (r"\bare not\b", "aren't"), (r"\bwas not\b", "wasn't"),
    (r"\bwere not\b", "weren't"), (r"\bhas not\b", "hasn't"), (r"\bhave not\b", "haven't"),
    (r"\bhad not\b", "hadn't"), (r"\bdid not\b", "didn't"), (r"\bdoes not\b", "doesn't"),
    (r"\bshould not\b", "shouldn't"), (r"\bwould not\b", "wouldn't"),
    (r"\bcould not\b", "couldn't"), (r"\bI am\b", "I'm"), (r"\bI have\b", "I've"),
    (r"\bI will\b", "I'll"), (r"\bit is\b", "it's"), (r"\bthat is\b", "that's"),
    (r"\bthere is\b", "there's"), (r"\bthey are\b", "they're"), (r"\bwe are\b", "we're"),
    (r"\byou are\b", "you're"), (r"\bhowever\b", "but"), (r"\btherefore\b", "so"),
]


def make_formal_fast(text):
    for pat, rep in _EXPAND:
        text = re.sub(pat, rep, text, flags=re.IGNORECASE)
    return text


def make_casual_fast(text):
    for pat, rep in _CONTRACT:
        text = re.sub(pat, rep, text, flags=re.IGNORECASE)
    return text


# ── Ollama (AI rewrite) ────────────────────────────────────────────────────
OLLAMA_BASE = "http://localhost:11434"
OLLAMA_PREFERRED = [
    "phi3:mini", "phi3", "gemma2:2b", "gemma2", "llama3.2:1b", "llama3.2",
    "llama3:latest", "llama3", "mistral:latest", "mistral",
]
OLLAMA_PROMPTS = {
    "fix": ("Fix the grammar, spelling and punctuation of the text below. "
            "Return ONLY the corrected text — no explanation, no quotes, no extra lines.\n\n{text}"),
    "formal": ("Rewrite the text below in a formal, professional tone. "
               "Return ONLY the rewritten text — no explanation, no quotes, no extra lines.\n\n{text}"),
    "casual": ("Rewrite the text below in a casual, friendly, conversational tone. "
               "Return ONLY the rewritten text — no explanation, no quotes, no extra lines.\n\n{text}"),
}


def ollama_find_model():
    """Return the best available Ollama model name, or None if Ollama isn't running."""
    try:
        with urllib.request.urlopen(
            urllib.request.Request(OLLAMA_BASE + "/api/tags"), timeout=2
        ) as resp:
            names = [m["name"] for m in json.loads(resp.read()).get("models", [])]
            for pref in OLLAMA_PREFERRED:
                root = pref.split(":")[0]
                for n in names:
                    if n.split(":")[0] == root:
                        return n
            return names[0] if names else None
    except Exception:
        return None


def ollama_call(prompt, model):
    """POST to Ollama chat API. Returns cleaned response text or raises."""
    payload = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        "options": {"temperature": 0.2, "num_predict": 500},
    }).encode()
    req = urllib.request.Request(
        OLLAMA_BASE + "/api/chat", data=payload,
        headers={"Content-Type": "application/json"}, method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        result = json.loads(resp.read())
    text = result.get("message", {}).get("content", "").strip()
    preambles = [
        "here's the corrected text:", "here's the rewritten text:",
        "here is the corrected text:", "corrected:", "result:", "output:",
        "improved:", "rewritten:",
    ]
    lower = text.lower()
    for p in preambles:
        if lower.startswith(p):
            text = text[len(p):].strip()
            break
    if len(text) >= 2 and text[0] in ('"', "'") and text[-1] == text[0]:
        text = text[1:-1]
    return text.strip()


def ai_rewrite(text, mode):
    """Rewrite via Ollama if available, else return None so callers can fall back."""
    model = ollama_find_model()
    if not model:
        return None
    try:
        out = ollama_call(OLLAMA_PROMPTS[mode].format(text=text), model)
        return out or None
    except Exception:
        return None


# ── Per-app profiles ───────────────────────────────────────────────────────
DEFAULT_PROFILES = {
    "default":                    {"cleanup": True,  "punctuate": False, "tone": "none"},
    "com.apple.mail":             {"cleanup": True,  "punctuate": True,  "tone": "formal"},
    "com.tinyspeck.slackmacgap":  {"cleanup": True,  "punctuate": False, "tone": "casual"},
    "net.whatsapp.WhatsApp":      {"cleanup": True,  "punctuate": False, "tone": "casual"},
    "com.microsoft.VSCode":       {"cleanup": False, "punctuate": False, "tone": "none"},
}


def get_profile(profiles, bundle_id):
    """Pick the rule for the focused app, falling back to 'default'."""
    profiles = profiles or {}
    return (profiles.get(bundle_id)
            or profiles.get("default")
            or DEFAULT_PROFILES["default"])
