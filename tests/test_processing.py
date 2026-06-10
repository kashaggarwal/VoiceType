"""
Unit tests for processing.py — the shared text-processing module used by
both worker.py and dashboard.py.

Run:  venv/bin/python -m unittest discover tests -v
"""

import io
import json
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import processing


# ── Custom vocabulary ──────────────────────────────────────────────────────
class TestBuildVocabPrompt(unittest.TestCase):
    def test_none_and_empty_return_none(self):
        self.assertIsNone(processing.build_vocab_prompt(None))
        self.assertIsNone(processing.build_vocab_prompt([]))

    def test_blank_words_are_dropped(self):
        self.assertIsNone(processing.build_vocab_prompt(["", "  ", None]))

    def test_words_joined_into_prompt(self):
        out = processing.build_vocab_prompt(["Kashish", "Higgsfield"])
        self.assertEqual(out, "Vocabulary: Kashish, Higgsfield.")

    def test_words_are_stripped(self):
        out = processing.build_vocab_prompt(["  VoiceType  "])
        self.assertEqual(out, "Vocabulary: VoiceType.")


# ── Shortcuts (text expansion) ─────────────────────────────────────────────
class TestApplyShortcuts(unittest.TestCase):
    def test_basic_replacement(self):
        out = processing.apply_shortcuts(
            "send it to my email", {"my email": "kaggarwal852@gmail.com"})
        self.assertEqual(out, "send it to kaggarwal852@gmail.com")

    def test_case_insensitive_trigger(self):
        out = processing.apply_shortcuts("My Email please", {"my email": "x@y.com"})
        self.assertEqual(out, "x@y.com please")

    def test_longer_trigger_wins(self):
        shortcuts = {"my email": "SHORT", "my email address": "LONG"}
        out = processing.apply_shortcuts("this is my email address", shortcuts)
        self.assertEqual(out, "this is LONG")

    def test_whole_word_only(self):
        # "sig" must not fire inside "signature"
        out = processing.apply_shortcuts("add my signature here", {"sig": "Best, K"})
        self.assertEqual(out, "add my signature here")

    def test_regex_metachars_in_trigger_are_literal(self):
        out = processing.apply_shortcuts("use c++ here", {"c++": "C-plus-plus"})
        self.assertEqual(out, "use C-plus-plus here")

    def test_backslash_in_expansion_is_safe(self):
        # A '\' or '\g' in the expansion must not be treated as a regex backref.
        out = processing.apply_shortcuts("my path", {"my path": r"C:\Users\g1"})
        self.assertEqual(out, r"C:\Users\g1")

    def test_empty_inputs_pass_through(self):
        self.assertEqual(processing.apply_shortcuts("", {"a": "b"}), "")
        self.assertEqual(processing.apply_shortcuts("hello", {}), "hello")
        self.assertEqual(processing.apply_shortcuts("hello", None), "hello")

    def test_blank_trigger_ignored(self):
        self.assertEqual(processing.apply_shortcuts("hello", {"  ": "X"}), "hello")

    def test_multiple_occurrences_all_replaced(self):
        out = processing.apply_shortcuts("brb now and brb later", {"brb": "be right back"})
        self.assertEqual(out, "be right back now and be right back later")


# ── Punctuation ────────────────────────────────────────────────────────────
class TestPunctuate(unittest.TestCase):
    def test_capitalizes_and_adds_period(self):
        self.assertEqual(processing.punctuate("hello world"), "Hello world.")

    def test_existing_terminal_punctuation_kept(self):
        self.assertEqual(processing.punctuate("really?"), "Really?")
        self.assertEqual(processing.punctuate("stop!"), "Stop!")
        self.assertEqual(processing.punctuate("Done."), "Done.")

    def test_empty_and_whitespace(self):
        self.assertEqual(processing.punctuate(""), "")
        self.assertEqual(processing.punctuate("   "), "")
        self.assertEqual(processing.punctuate(None), "")


# ── Fast tone conversion ───────────────────────────────────────────────────
class TestToneFast(unittest.TestCase):
    def test_formal_expands_contractions(self):
        out = processing.make_formal_fast("I'm sure it's fine, don't worry")
        self.assertEqual(out, "I am sure it is fine, do not worry")

    def test_formal_expands_slang(self):
        out = processing.make_formal_fast("I wanna go, gonna be late, yeah")
        self.assertEqual(out, "I want to go, going to be late, yes")

    def test_casual_contracts(self):
        out = processing.make_casual_fast("I am sure it is fine, do not worry")
        self.assertEqual(out, "I'm sure it's fine, don't worry")

    def test_casual_softens_connectives(self):
        out = processing.make_casual_fast("however that is wrong, therefore we stop")
        self.assertEqual(out, "but that's wrong, so we stop")

    def test_roundtrip_stability(self):
        casual = "don't stop, it's fine"
        self.assertEqual(
            processing.make_casual_fast(processing.make_formal_fast(casual)), casual)


# ── Per-app profiles ───────────────────────────────────────────────────────
class TestGetProfile(unittest.TestCase):
    def test_known_bundle(self):
        p = processing.get_profile(processing.DEFAULT_PROFILES, "com.apple.mail")
        self.assertEqual(p["tone"], "formal")
        self.assertTrue(p["punctuate"])

    def test_unknown_bundle_falls_back_to_default(self):
        p = processing.get_profile(processing.DEFAULT_PROFILES, "com.unknown.app")
        self.assertEqual(p, processing.DEFAULT_PROFILES["default"])

    def test_none_bundle_falls_back(self):
        p = processing.get_profile(processing.DEFAULT_PROFILES, None)
        self.assertEqual(p, processing.DEFAULT_PROFILES["default"])

    def test_empty_profiles_uses_builtin_default(self):
        p = processing.get_profile({}, "com.apple.mail")
        self.assertEqual(p, processing.DEFAULT_PROFILES["default"])
        p = processing.get_profile(None, "anything")
        self.assertEqual(p, processing.DEFAULT_PROFILES["default"])

    def test_vscode_disables_cleanup(self):
        p = processing.get_profile(processing.DEFAULT_PROFILES, "com.microsoft.VSCode")
        self.assertFalse(p["cleanup"])


# ── Ollama (mocked network) ────────────────────────────────────────────────
def _fake_response(body_dict):
    resp = mock.MagicMock()
    resp.read.return_value = json.dumps(body_dict).encode()
    resp.__enter__ = lambda s: s
    resp.__exit__ = mock.MagicMock(return_value=False)
    return resp


class TestOllama(unittest.TestCase):
    def test_find_model_prefers_small_models(self):
        body = {"models": [{"name": "llama3:latest"}, {"name": "phi3:mini"}]}
        with mock.patch.object(processing.urllib.request, "urlopen",
                               return_value=_fake_response(body)):
            self.assertEqual(processing.ollama_find_model(), "phi3:mini")

    def test_find_model_none_when_unreachable(self):
        with mock.patch.object(processing.urllib.request, "urlopen",
                               side_effect=OSError("connection refused")):
            self.assertIsNone(processing.ollama_find_model())

    def test_find_model_falls_back_to_first_available(self):
        body = {"models": [{"name": "qwen2:7b"}]}
        with mock.patch.object(processing.urllib.request, "urlopen",
                               return_value=_fake_response(body)):
            self.assertEqual(processing.ollama_find_model(), "qwen2:7b")

    def test_call_strips_preamble_and_quotes(self):
        body = {"message": {"content": 'Here\'s the corrected text: "Hello there."'}}
        with mock.patch.object(processing.urllib.request, "urlopen",
                               return_value=_fake_response(body)):
            self.assertEqual(processing.ollama_call("p", "m"), "Hello there.")

    def test_ai_rewrite_returns_none_without_ollama(self):
        with mock.patch.object(processing, "ollama_find_model", return_value=None):
            self.assertIsNone(processing.ai_rewrite("hi", "formal"))

    def test_ai_rewrite_returns_none_on_error(self):
        with mock.patch.object(processing, "ollama_find_model", return_value="m"), \
             mock.patch.object(processing, "ollama_call", side_effect=OSError("boom")):
            self.assertIsNone(processing.ai_rewrite("hi", "formal"))

    def test_ai_rewrite_returns_text_on_success(self):
        with mock.patch.object(processing, "ollama_find_model", return_value="m"), \
             mock.patch.object(processing, "ollama_call", return_value="Rewritten."):
            self.assertEqual(processing.ai_rewrite("hi", "casual"), "Rewritten.")


if __name__ == "__main__":
    unittest.main(verbosity=2)
