#!/usr/bin/env python3
"""
VoiceType Dashboard — Flow-style UI using WKWebView.
Runs inside the same process as menubar.py.
"""

import re
import json
import os
import threading
import datetime
import urllib.request
import urllib.error
import AppKit
import objc
from Foundation import NSObject, NSMakeRect
from WebKit import WKWebView, WKWebViewConfiguration, WKUserContentController

# ── Config helpers ────────────────────────────────────────────────────────
_CONFIG_PATH = os.path.expanduser("~/.voicetype/config.json")
_DEFAULT_FILLERS = ["um", "uh", "hmm", "hm", "er"]

def _load_filler_words():
    try:
        with open(_CONFIG_PATH) as f:
            return json.load(f).get("filler_words", _DEFAULT_FILLERS)
    except Exception:
        return list(_DEFAULT_FILLERS)

def _save_filler_words(words):
    os.makedirs(os.path.dirname(_CONFIG_PATH), exist_ok=True)
    try:
        with open(_CONFIG_PATH) as f:
            cfg = json.load(f)
    except Exception:
        cfg = {}
    cfg["filler_words"] = words
    with open(_CONFIG_PATH, "w") as f:
        json.dump(cfg, f, indent=2)

# ── Persistent daily word-count stats ─────────────────────────────────────
_STATS_PATH = os.path.expanduser("~/.voicetype/stats.json")

# Single source of truth for the app version shown in the dashboard.
# release.sh keeps this in sync with the git tag / app bundle version.
VERSION = "1.3"

def _load_daily_stats():
    try:
        with open(_STATS_PATH) as f:
            data = json.load(f)
            cutoff = (datetime.date.today() - datetime.timedelta(days=730)).isoformat()
            return {k: v for k, v in data.items() if k >= cutoff}
    except Exception:
        return {}

def _save_daily_stats(stats):
    os.makedirs(os.path.dirname(_STATS_PATH), exist_ok=True)
    with open(_STATS_PATH, "w") as f:
        json.dump(stats, f, indent=2)

def _calc_period_words(stats):
    today = datetime.date.today()
    week_start  = today - datetime.timedelta(days=today.weekday())
    month_start = today.replace(day=1)
    year_start  = today.replace(month=1, day=1)
    tots = {"today": 0, "week": 0, "month": 0, "year": 0}
    for date_str, words in stats.items():
        try:
            d = datetime.date.fromisoformat(date_str)
        except ValueError:
            continue
        if d == today:
            tots["today"] += words
        if d >= week_start:
            tots["week"] += words
        if d >= month_start:
            tots["month"] += words
        if d >= year_start:
            tots["year"] += words
    # Always include the per-month breakdown so every push site that sends
    # period stats keeps the "By Month" strip populated (not just the initial
    # load). Otherwise a live update after dictation would blank the strip.
    tots["months"] = _calc_monthly_words(stats)
    return tots

_MONTH_ABBR = ["JAN","FEB","MAR","APR","MAY","JUN",
               "JUL","AUG","SEP","OCT","NOV","DEC"]

def _calc_monthly_words(stats, limit=12):
    """Total words per calendar month, most recent first (up to `limit` months)."""
    months = {}
    for date_str, words in stats.items():
        try:
            d = datetime.date.fromisoformat(date_str)
        except ValueError:
            continue
        key = (d.year, d.month)
        months[key] = months.get(key, 0) + words
    ordered = sorted(months.keys(), reverse=True)[:limit]
    return [{"label": _MONTH_ABBR[m - 1], "year": y, "words": months[(y, m)]}
            for (y, m) in ordered]

LANGUAGES = [
    ("English",     "en"),
    ("Mixed (Auto per recording)", "mixed"),
    ("Auto-detect", ""),
    ("Spanish",     "es"),
    ("French",      "fr"),
    ("German",      "de"),
    ("Hindi",       "hi"),
    ("Portuguese",  "pt"),
    ("Italian",     "it"),
    ("Arabic",      "ar"),
    ("Japanese",    "ja"),
    ("Chinese",     "zh"),
    ("Korean",      "ko"),
]

LANG_NAMES = {code: name for name, code in LANGUAGES}

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en" data-theme="auto">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>VoiceType</title>
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }

  :root {
    --bg: #f0ede8;
    --surface: #ffffff;
    --surface-2: #f7f5f2;
    --border: #e8e5e0;
    --border-2: #ece9e4;
    --text: #1a1a1a;
    --text-2: #555;
    --text-3: #888;
    --text-4: #bbb;
    --accent: #6d28d9;
    --accent-bg: #ede9fe;
    --danger: #ef4444;
    --hover-bg: #f0ede8;
    --input-bg: #fafafa;
    --chip-bg: #f0ede8;
  }
  html[data-theme="dark"] {
    --bg: #18181b;
    --surface: #232327;
    --surface-2: #2a2a2f;
    --border: #36363c;
    --border-2: #2e2e34;
    --text: #f4f4f5;
    --text-2: #c4c4c8;
    --text-3: #9a9aa0;
    --text-4: #6b6b72;
    --accent: #a78bfa;
    --accent-bg: #312e4a;
    --danger: #f87171;
    --hover-bg: #2a2a2f;
    --input-bg: #2a2a2f;
    --chip-bg: #2a2a2f;
  }
  @media (prefers-color-scheme: dark) {
    html[data-theme="auto"] {
      --bg: #18181b;
      --surface: #232327;
      --surface-2: #2a2a2f;
      --border: #36363c;
      --border-2: #2e2e34;
      --text: #f4f4f5;
      --text-2: #c4c4c8;
      --text-3: #9a9aa0;
      --text-4: #6b6b72;
      --accent: #a78bfa;
      --accent-bg: #312e4a;
      --danger: #f87171;
      --hover-bg: #2a2a2f;
      --input-bg: #2a2a2f;
      --chip-bg: #2a2a2f;
    }
  }

  body {
    font-family: -apple-system, BlinkMacSystemFont, "SF Pro Text", "Helvetica Neue", sans-serif;
    background: var(--bg);
    display: flex;
    height: 100vh;
    overflow: hidden;
    color: var(--text);
    -webkit-font-smoothing: antialiased;
  }

  /* ── Sidebar ── */
  .sidebar {
    width: 210px;
    min-width: 210px;
    background: var(--surface);
    border-right: 1px solid var(--border);
    display: flex;
    flex-direction: column;
    padding: 16px 12px;
    height: 100vh;
  }

  .logo {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 4px 8px 16px;
    font-size: 17px;
    font-weight: 700;
    letter-spacing: -0.3px;
    color: var(--text);
  }
  .logo-icon { font-size: 20px; }

  nav { flex: 1; display: flex; flex-direction: column; gap: 2px; }

  .nav-item {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 8px 10px;
    border-radius: 8px;
    cursor: pointer;
    font-size: 14px;
    font-weight: 500;
    color: var(--text-2);
    transition: background 0.1s;
    -webkit-user-select: none;
  }
  .nav-item:hover { background: var(--hover-bg); color: var(--text); }
  .nav-item.active { background: var(--hover-bg); color: var(--text); }
  .nav-icon { font-size: 15px; width: 20px; text-align: center; }

  .sidebar-bottom { margin-top: auto; display: flex; flex-direction: column; gap: 10px; }

  .status-card {
    background: var(--surface-2);
    border: 1px solid var(--border);
    border-radius: 10px;
    padding: 12px 14px;
  }
  .status-dot {
    display: inline-block;
    width: 8px; height: 8px;
    border-radius: 50%;
    margin-right: 6px;
    background: #9ca3af;
    transition: background 0.3s;
  }
  .status-dot.off        { background: #9ca3af; }
  .status-dot.paused     { background: #f59e0b; }
  .status-dot.loading    { background: #f59e0b; }
  .status-dot.ready      { background: #22c55e; animation: pulse 2s infinite; }
  .status-dot.recording  { background: #ef4444; animation: pulse 0.8s infinite; }
  .status-dot.transcribing { background: #f97316; animation: pulse 1s infinite; }

  @keyframes pulse {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.4; }
  }

  .status-label { font-size: 12px; font-weight: 600; color: var(--text); }
  .status-sub { font-size: 11px; color: var(--text-3); margin-top: 3px; }

  .toggle-btn {
    width: 100%;
    padding: 11px;
    background: #1a1a1a;
    color: #ffffff;
    border: none;
    border-radius: 10px;
    font-size: 14px;
    font-weight: 600;
    cursor: pointer;
    transition: background 0.15s, transform 0.1s;
    -webkit-user-select: none;
  }
  .toggle-btn:hover { background: #333; }
  .toggle-btn:active { transform: scale(0.98); }
  .toggle-btn.on     { background: #1a1a1a; }
  .toggle-btn.off    { background: #6d28d9; }
  .toggle-btn.resume { background: #16a34a; }
  .toggle-btn.resume:hover { background: #15803d; }

  .stop-btn {
    width: 100%;
    padding: 9px;
    background: transparent;
    color: #ef4444;
    border: 1px solid #fca5a5;
    border-radius: 10px;
    font-size: 13px;
    font-weight: 600;
    cursor: pointer;
    transition: background 0.15s, border-color 0.15s;
    -webkit-user-select: none;
    font-family: inherit;
  }
  .stop-btn:hover { background: #fff0f0; border-color: #ef4444; }

  /* ── Main content ── */
  .main {
    flex: 1;
    display: flex;
    flex-direction: column;
    overflow: hidden;
    padding: 24px 28px;
    gap: 20px;
  }

  .page { display: none; flex-direction: column; flex: 1; min-height: 0; overflow: hidden; gap: 20px; }
  .page.active { display: flex; }

  .welcome { font-size: 22px; font-weight: 700; letter-spacing: -0.4px; }

  .top-row { display: flex; gap: 16px; align-items: flex-start; }

  .hero-card {
    flex: 1;
    background: #1a1a1a;
    border-radius: 14px;
    padding: 24px 28px;
    color: white;
    min-height: 130px;
    position: relative;
    overflow: hidden;
    display: flex;
    flex-direction: column;
    justify-content: space-between;
  }
  .hero-card::after {
    content: "🎙";
    position: absolute;
    right: 24px;
    top: 50%;
    transform: translateY(-50%);
    font-size: 56px;
    opacity: 0.15;
  }
  .hero-title { font-size: 20px; font-weight: 700; letter-spacing: -0.3px; }
  .hero-sub { font-size: 13px; color: #aaa; margin-top: 6px; }
  .hero-hotkey {
    display: inline-block;
    margin-top: 14px;
    background: rgba(255,255,255,0.12);
    border: 1px solid rgba(255,255,255,0.2);
    border-radius: 7px;
    padding: 5px 12px;
    font-size: 13px;
    font-weight: 500;
    color: #eee;
  }

  .stats-card {
    width: 190px;
    min-width: 190px;
    background: var(--surface);
    border-radius: 14px;
    padding: 20px 22px;
    border: 1px solid var(--border);
    display: flex;
    flex-direction: column;
    gap: 10px;
  }
  .stat-num { font-size: 22px; font-weight: 700; letter-spacing: -0.5px; color: var(--text); }
  .stat-label { font-size: 11px; color: var(--text-3); margin-top: 1px; }

  .history-section { flex: 1; min-height: 0; display: flex; flex-direction: column; overflow: hidden; }

  /* Home page scrolls as one unit (hero + stats + time-saved + history).
     Without this, the taller time-saved card squeezes the history list to
     zero height and the page can't scroll. The History tab keeps its own
     inner-scroll behavior (overrides below are scoped to #page-home). */
  #page-home { overflow-y: auto; overflow-x: hidden; }
  #page-home .history-section { flex: none; }
  #page-home .history-scroll { flex: none; overflow: visible; }

  .section-header {
    font-size: 11px;
    font-weight: 600;
    color: var(--text-3);
    letter-spacing: 0.8px;
    text-transform: uppercase;
    margin-bottom: 8px;
  }

  .history-scroll { flex: 1; overflow-y: auto; display: flex; flex-direction: column; gap: 2px; }
  .history-scroll::-webkit-scrollbar { width: 4px; }
  .history-scroll::-webkit-scrollbar-track { background: transparent; }
  .history-scroll::-webkit-scrollbar-thumb { background: #d1d5db; border-radius: 2px; }

  .date-group { margin-bottom: 6px; }
  .date-label {
    font-size: 11px;
    font-weight: 600;
    color: var(--text-3);
    letter-spacing: 0.6px;
    text-transform: uppercase;
    padding: 12px 0 6px;
  }

  .history-item {
    display: flex;
    gap: 16px;
    background: var(--surface);
    border-radius: 10px;
    padding: 12px 16px;
    margin-bottom: 2px;
    border: 1px solid var(--border-2);
    transition: border-color 0.15s;
  }
  .history-item:hover { border-color: var(--border); }

  .item-time { font-size: 13px; color: var(--text-3); min-width: 70px; padding-top: 1px; font-variant-numeric: tabular-nums; }
  .item-text { font-size: 14px; color: var(--text); line-height: 1.5; flex: 1; }

  .empty-state {
    flex: 1;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    color: var(--text-4);
    gap: 8px;
    padding: 40px;
    text-align: center;
  }
  .empty-icon { font-size: 40px; opacity: 0.5; }
  .empty-title { font-size: 15px; font-weight: 600; color: var(--text-3); }
  .empty-sub { font-size: 13px; color: var(--text-4); }

  /* ── Settings page ── */
  .settings-section { display: flex; flex-direction: column; gap: 8px; margin-bottom: 24px; }
  .settings-title { font-size: 13px; font-weight: 600; color: var(--text-3); text-transform: uppercase; letter-spacing: 0.6px; margin-bottom: 4px; }
  .settings-card {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 12px;
    overflow: hidden;
  }
  .settings-row {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 14px 18px;
    border-bottom: 1px solid var(--border);
    font-size: 14px;
  }
  .settings-row:last-child { border-bottom: none; }
  .settings-row-label { font-weight: 500; color: var(--text); }
  .settings-row-sub { font-size: 12px; color: var(--text-3); margin-top: 2px; }

  select {
    border: 1px solid var(--border);
    border-radius: 7px;
    padding: 6px 10px;
    font-size: 13px;
    background: var(--input-bg);
    color: var(--text);
    outline: none;
    cursor: pointer;
    font-family: inherit;
  }
  select:focus { border-color: var(--accent); }

  .clear-btn {
    padding: 7px 14px;
    background: transparent;
    border: 1px solid var(--border);
    border-radius: 8px;
    font-size: 13px;
    font-weight: 500;
    color: var(--text-2);
    cursor: pointer;
    font-family: inherit;
    transition: all 0.15s;
  }
  .clear-btn:hover { background: #fff0f0; border-color: #fca5a5; color: #ef4444; }

  /* ── Filler word chips ── */
  .filler-area { padding: 14px 18px; border-top: 1px solid var(--border); }
  .filler-chips { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 10px; min-height: 28px; }
  .filler-chip {
    display: inline-flex; align-items: center; gap: 5px;
    background: var(--chip-bg); border: 1px solid var(--border); border-radius: 20px;
    padding: 3px 10px 3px 12px; font-size: 13px; color: var(--text);
  }
  .filler-chip-x {
    cursor: pointer; color: var(--text-3); font-size: 15px; line-height: 1;
    padding: 0 2px;
  }
  .filler-chip-x:hover { color: #ef4444; }
  .filler-add-row { display: flex; gap: 8px; align-items: center; }
  .filler-input {
    flex: 1; border: 1px solid var(--border); border-radius: 8px;
    padding: 6px 10px; font-size: 13px; font-family: inherit;
    outline: none; background: var(--input-bg); color: var(--text);
  }
  .filler-input:focus { border-color: var(--accent); }
  .filler-add-btn {
    padding: 6px 14px; background: #1a1a1a; color: white;
    border: none; border-radius: 8px; font-size: 13px; font-weight: 500;
    cursor: pointer; font-family: inherit; white-space: nowrap;
  }
  .filler-add-btn:hover { background: #333; }

  /* ── Voice command reference ── */
  .cmd-table { width: 100%; border-collapse: collapse; }
  .cmd-table td { padding: 8px 18px; font-size: 13px; border-bottom: 1px solid var(--border); color: var(--text-2); }
  .cmd-table tr:last-child td { border-bottom: none; }
  .cmd-trigger { font-weight: 600; color: var(--text); font-family: monospace; }
  .cmd-arrow { color: var(--text-4); padding: 0 4px; }
  .cmd-desc { color: var(--text-2); }

  /* ── Command toast ── */
  .cmd-toast {
    position: fixed; bottom: 24px; left: 50%; transform: translateX(-50%);
    background: #1a1a1a; color: white; padding: 8px 18px;
    border-radius: 20px; font-size: 13px; font-weight: 500;
    opacity: 0; transition: opacity 0.2s; pointer-events: none;
    white-space: nowrap; z-index: 999;
  }
  .cmd-toast.visible { opacity: 1; }

  /* ── Toggle switch ── */
  .toggle-switch {
    position: relative;
    width: 44px;
    height: 24px;
    cursor: pointer;
    flex-shrink: 0;
  }
  .toggle-switch input { opacity: 0; width: 0; height: 0; }
  .toggle-switch .slider {
    position: absolute;
    top: 0; left: 0; right: 0; bottom: 0;
    background: #d1d5db;
    border-radius: 24px;
    transition: background 0.2s;
  }
  .toggle-switch .slider:before {
    content: "";
    position: absolute;
    width: 18px; height: 18px;
    left: 3px; bottom: 3px;
    background: white;
    border-radius: 50%;
    transition: transform 0.2s;
    box-shadow: 0 1px 3px rgba(0,0,0,0.2);
  }
  .toggle-switch input:checked + .slider { background: #6d28d9; }
  .toggle-switch input:checked + .slider:before { transform: translateX(20px); }

  /* ── Time saved ── */
  .stat-saved-item { border-top: 1px solid var(--border); padding-top: 10px; margin-top: 2px; }
  .saved-num { color: #16a34a !important; }
  .stat-sublabel { font-size: 10px; color: var(--text-4); margin-top: 1px; }

  .time-saved-card {
    background: linear-gradient(135deg, #f0fdf4, #dcfce7);
    border: 1px solid #86efac;
    border-radius: 14px;
    padding: 14px 18px 10px;
    display: none;
  }
  .time-saved-card.has-data { display: block; }
  .time-saved-header {
    display: flex;
    align-items: center;
    gap: 7px;
    font-size: 13px;
    font-weight: 700;
    color: #15803d;
    margin-bottom: 10px;
  }
  .time-saved-header .ts-icon { font-size: 15px; }
  .time-saved-rows { display: flex; gap: 0; }
  .ts-col {
    flex: 1;
    display: flex;
    flex-direction: column;
    align-items: center;
    padding: 6px 4px;
    border-radius: 10px;
    transition: background 0.15s;
  }
  .ts-col:not(:last-child) { border-right: 1px solid #bbf7d0; }
  .ts-value {
    font-size: 16px;
    font-weight: 800;
    color: #16a34a;
    letter-spacing: -0.5px;
    line-height: 1.1;
  }
  .ts-value.ts-zero { color: #9ca3af; font-weight: 500; font-size: 14px; }
  .ts-label {
    font-size: 10px;
    font-weight: 600;
    color: #15803d;
    margin-top: 3px;
    text-transform: uppercase;
    letter-spacing: 0.3px;
    opacity: 0.75;
  }

  /* ── By-month strip ── */
  .ts-months-wrap { margin-top: 12px; border-top: 1px solid #bbf7d0; padding-top: 10px; display: none; }
  .ts-months-wrap.has-months { display: block; }
  .ts-months-header {
    font-size: 10px;
    font-weight: 700;
    color: #15803d;
    text-transform: uppercase;
    letter-spacing: 0.4px;
    opacity: 0.75;
    margin-bottom: 8px;
  }
  .ts-months-strip {
    display: flex;
    gap: 8px;
    overflow-x: auto;
    padding-bottom: 4px;
    scrollbar-width: thin;
  }
  .ts-months-strip::-webkit-scrollbar { height: 4px; }
  .ts-months-strip::-webkit-scrollbar-track { background: transparent; }
  .ts-months-strip::-webkit-scrollbar-thumb { background: #86efac; border-radius: 2px; }
  .ts-month {
    flex: 0 0 auto;
    min-width: 62px;
    background: rgba(255,255,255,0.55);
    border: 1px solid #bbf7d0;
    border-radius: 9px;
    padding: 8px 10px;
    display: flex;
    flex-direction: column;
    align-items: center;
  }
  .ts-month-value { font-size: 14px; font-weight: 800; color: #16a34a; letter-spacing: -0.4px; line-height: 1.1; }
  .ts-month-label { font-size: 9px; font-weight: 600; color: #15803d; margin-top: 3px; letter-spacing: 0.3px; opacity: 0.7; }

  /* ── Tone selector ── */
  .tone-row { display: flex; gap: 6px; flex-wrap: wrap; }
  .tone-btn {
    padding: 6px 14px;
    border-radius: 20px;
    border: 1.5px solid var(--border);
    background: var(--surface);
    font-size: 13px;
    font-weight: 500;
    color: var(--text-2);
    cursor: pointer;
    font-family: inherit;
    transition: all 0.15s;
    -webkit-user-select: none;
  }
  .tone-btn:hover { border-color: var(--accent); color: var(--accent); }
  .tone-btn.active {
    background: #6d28d9;
    border-color: #6d28d9;
    color: white;
  }

  /* ── Grammar Fix page ── */
  .grammar-layout {
    display: flex;
    gap: 20px;
    flex: 1;
    overflow: hidden;
    min-height: 0;
  }
  .grammar-col {
    flex: 1;
    display: flex;
    flex-direction: column;
    gap: 10px;
    min-width: 0;
  }
  .grammar-col-label {
    font-size: 11px;
    font-weight: 600;
    color: var(--text-3);
    letter-spacing: 0.8px;
    text-transform: uppercase;
  }
  .grammar-textarea {
    flex: 1;
    width: 100%;
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 10px;
    padding: 16px;
    font-size: 14px;
    line-height: 1.6;
    font-family: inherit;
    color: var(--text);
    resize: none;
    outline: none;
    transition: border-color 0.15s;
    min-height: 0;
  }
  .grammar-textarea:focus { border-color: var(--accent); }
  .grammar-output {
    flex: 1;
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 10px;
    padding: 16px;
    font-size: 14px;
    line-height: 1.6;
    color: var(--text);
    overflow-y: auto;
    min-height: 0;
  }
  .grammar-output.empty { color: var(--text-4); font-style: italic; }
  .grammar-word-count { font-size: 12px; color: var(--text-4); }
  .grammar-btn-row { display: flex; justify-content: center; gap: 10px; align-items: center; }
  .grammar-fix-btn {
    padding: 10px 28px;
    background: #1a1a1a;
    color: white;
    border: none;
    border-radius: 10px;
    font-size: 14px;
    font-weight: 600;
    cursor: pointer;
    font-family: inherit;
    transition: background 0.15s, transform 0.1s;
    -webkit-user-select: none;
  }
  .grammar-fix-btn:hover { background: #333; }
  .grammar-fix-btn:active { transform: scale(0.98); }
  .grammar-copy-btn {
    padding: 7px 16px;
    background: transparent;
    border: 1px solid var(--border);
    border-radius: 8px;
    font-size: 13px;
    font-weight: 500;
    color: var(--text-2);
    cursor: pointer;
    font-family: inherit;
    transition: all 0.15s;
  }
  .grammar-copy-btn:hover { background: var(--hover-bg); color: var(--text); }
  .grammar-change-badge {
    font-size: 12px;
    color: var(--accent);
    font-weight: 600;
    background: var(--accent-bg);
    border-radius: 6px;
    padding: 3px 10px;
  }
  span.changed {
    background: var(--accent-bg);
    color: var(--accent);
    border-radius: 3px;
    padding: 0 2px;
  }
  .ai-badge {
    display: inline-flex;
    align-items: center;
    gap: 5px;
    font-size: 11px;
    font-weight: 600;
    padding: 3px 10px;
    border-radius: 20px;
    border: 1px solid var(--border);
    color: var(--text-3);
    background: var(--surface);
    letter-spacing: 0.3px;
    transition: all 0.2s;
  }
  .ai-badge.ai-on {
    color: #4ade80;
    border-color: rgba(74,222,128,0.35);
    background: rgba(74,222,128,0.08);
  }
  .grammar-subtitle {
    font-size: 13px;
    color: var(--text-3);
    margin-top: 2px;
    margin-bottom: 4px;
  }
</style>
</head>
<body>

<!-- Sidebar -->
<div class="sidebar">
  <div class="logo">
    <span class="logo-icon">🎤</span>
    VoiceType
  </div>

  <nav>
    <div class="nav-item active" onclick="showPage(&quot;home&quot;)" id="nav-home">
      <span class="nav-icon">⊞</span> Home
    </div>
    <div class="nav-item" onclick="showPage(&quot;history&quot;)" id="nav-history">
      <span class="nav-icon">☰</span> History
    </div>
    <div class="nav-item" onclick="showPage(&quot;grammar&quot;)" id="nav-grammar">
      <span class="nav-icon">✏️</span> Grammar Fix
    </div>
    <div class="nav-item" onclick="showPage(&quot;settings&quot;)" id="nav-settings">
      <span class="nav-icon">⚙</span> Settings
    </div>
  </nav>

  <div class="sidebar-bottom">
    <div class="status-card">
      <div>
        <span class="status-dot off" id="status-dot"></span>
        <span class="status-label" id="status-label">Off</span>
      </div>
      <div class="status-sub" id="status-sub">Click Turn ON to start</div>
    </div>
    <button class="toggle-btn off" id="toggle-btn" onclick="handleToggle()">Turn ON</button>
    <button class="stop-btn" id="stop-btn" onclick="handleStop()" style="display:none;">■ Stop</button>
  </div>
</div>

<!-- Main -->
<div class="main">

  <!-- Home page -->
  <div class="page active" id="page-home">
    <div class="welcome" id="welcome-text">Welcome back, Kashish</div>

    <div class="top-row">
      <div class="hero-card">
        <div>
          <div class="hero-title" id="hero-title">Hold Right ⌥ to dictate</div>
          <div class="hero-sub" id="hero-sub">VoiceType transcribes your voice instantly and pastes it anywhere.</div>
        </div>
        <div class="hero-hotkey">Hold Right ⌥ → speak → release → text pastes</div>
      </div>

      <div class="stats-card">
        <div class="stat-item">
          <div class="stat-num" id="stat-words">0</div>
          <div class="stat-label">words today</div>
        </div>
        <div class="stat-item">
          <div class="stat-num" id="stat-count">0</div>
          <div class="stat-label">transcriptions</div>
        </div>
        <div class="stat-item">
          <div class="stat-num" id="stat-wpm">—</div>
          <div class="stat-label">avg WPM</div>
        </div>
        <div class="stat-item">
          <div class="stat-num" id="stat-lang">EN</div>
          <div class="stat-label">language</div>
        </div>
        <div class="stat-item stat-saved-item">
          <div class="stat-num saved-num" id="stat-saved">—</div>
          <div class="stat-label">typing time saved</div>
          <div class="stat-sublabel">vs avg typist (40 wpm)</div>
        </div>
      </div>
    </div>

    <!-- Time Saved breakdown card -->
    <div class="time-saved-card" id="time-saved-card">
      <div class="time-saved-header">
        <span class="ts-icon">⚡</span> Typing Time Saved
      </div>
      <div class="time-saved-rows">
        <div class="ts-col">
          <div class="ts-value ts-zero" id="ts-today">—</div>
          <div class="ts-label">Today</div>
        </div>
        <div class="ts-col">
          <div class="ts-value ts-zero" id="ts-week">—</div>
          <div class="ts-label">This Week</div>
        </div>
        <div class="ts-col">
          <div class="ts-value ts-zero" id="ts-month">—</div>
          <div class="ts-label">This Month</div>
        </div>
        <div class="ts-col">
          <div class="ts-value ts-zero" id="ts-year">—</div>
          <div class="ts-label">This Year</div>
        </div>
      </div>
      <div class="ts-months-wrap" id="ts-months-wrap">
        <div class="ts-months-header">By Month</div>
        <div class="ts-months-strip" id="ts-months-strip"></div>
      </div>
    </div>

    <!-- Today's history -->
    <div class="history-section">
      <div class="section-header">Today</div>
      <div class="history-scroll" id="today-scroll">
        <div class="empty-state" id="empty-state">
          <div class="empty-icon">🎙</div>
          <div class="empty-title">No transcriptions yet</div>
          <div class="empty-sub">Turn ON and hold Right ⌥ to speak</div>
        </div>
      </div>
    </div>
  </div>

  <!-- History page -->
  <div class="page" id="page-history">
    <div class="welcome">History</div>
    <div class="history-section" style="margin-top:0">
      <div class="history-scroll" id="history-scroll">
        <div class="empty-state">
          <div class="empty-icon">📋</div>
          <div class="empty-title">No history yet</div>
          <div class="empty-sub">Your transcriptions will appear here</div>
        </div>
      </div>
    </div>
  </div>

  <!-- Grammar Fix page -->
  <div class="page" id="page-grammar">
    <div style="display:flex;align-items:center;justify-content:space-between;">
      <div>
        <div class="welcome">Grammar Fix</div>
        <div class="grammar-subtitle" id="grammar-subtitle">Select a tone, paste your text, and transform it.</div>
      </div>
      <span class="ai-badge" id="ai-badge" title="Checking for Ollama…">⟳ Checking AI…</span>
    </div>

    <!-- Tone selector -->
    <div class="tone-row" id="tone-row">
      <button class="tone-btn active" onclick="setTone(&quot;fix&quot;,this)">✓ Fix Grammar</button>
      <button class="tone-btn" onclick="setTone(&quot;formal&quot;,this)">🎩 Formal</button>
      <button class="tone-btn" onclick="setTone(&quot;casual&quot;,this)">😊 Casual</button>
      <button class="tone-btn" onclick="setTone(&quot;shorter&quot;,this)">✂️ Shorter</button>
      <button class="tone-btn" onclick="setTone(&quot;improve&quot;,this)">✨ Improve</button>
    </div>

    <div class="grammar-layout">
      <div class="grammar-col">
        <div class="grammar-col-label">Input</div>
        <textarea class="grammar-textarea" id="grammar-input" placeholder="Paste or type your text here…" oninput="updateWordCount()"></textarea>
        <div style="display:flex;justify-content:space-between;align-items:center;">
          <span class="grammar-word-count" id="grammar-word-count">0 words</span>
        </div>
        <div class="grammar-btn-row">
          <button class="grammar-fix-btn" id="grammar-fix-btn" onclick="handleGrammarFix()">Fix Grammar →</button>
        </div>
      </div>
      <div class="grammar-col">
        <div class="grammar-col-label">Output</div>
        <div class="grammar-output empty" id="grammar-output">Corrected text will appear here.</div>
        <div style="display:flex;justify-content:space-between;align-items:center;min-height:28px;">
          <span id="grammar-change-badge" style="display:none;" class="grammar-change-badge"></span>
          <button class="grammar-copy-btn" id="grammar-copy-btn" style="display:none;" onclick="copyGrammarResult()">Copy</button>
        </div>
      </div>
    </div>
  </div>

  <!-- Settings page -->
  <div class="page" id="page-settings">
    <div class="welcome">Settings</div>

    <div style="overflow-y:auto;flex:1;">
      <div class="settings-section">
        <div class="settings-title">Transcription</div>
        <div class="settings-card">
          <div class="settings-row">
            <div>
              <div class="settings-row-label">Language</div>
              <div class="settings-row-sub">Restart required when changed</div>
            </div>
            <select id="lang-select" onchange="handleLanguage()">
              __LANG_OPTIONS__
            </select>
          </div>
          <div class="settings-row">
            <div>
              <div class="settings-row-label">AI Model</div>
              <div class="settings-row-sub">Faster = quicker results · Accurate = better quality</div>
            </div>
            <select id="model-select" onchange="handleModel()">
              <option value="mlx-community/whisper-small-mlx" selected>Small — fast (~4s) ✦</option>
              <option value="mlx-community/whisper-medium-mlx">Medium — balanced (~10s)</option>
              <option value="mlx-community/whisper-large-v3-mlx">Large v3 — best quality (~20s)</option>
            </select>
          </div>
        </div>
      </div>

      <div class="settings-section">
        <div class="settings-title">Processing</div>
        <div class="settings-card">
          <div class="settings-row">
            <div>
              <div class="settings-row-label">Auto Cleanup</div>
              <div class="settings-row-sub">Removes filler words, capitalizes first letter</div>
            </div>
            <label class="toggle-switch">
              <input type="checkbox" id="cleanup-toggle" onchange="handleCleanupToggle()">
              <span class="slider"></span>
            </label>
          </div>
          <div class="settings-row">
            <div>
              <div class="settings-row-label">✦ Auto Grammar Fix</div>
              <div class="settings-row-sub">Fixes grammar, spelling &amp; punctuation on every dictation — before it pastes</div>
            </div>
            <label class="toggle-switch">
              <input type="checkbox" id="grammar-auto-toggle" onchange="handleGrammarAutoToggle()">
              <span class="slider"></span>
            </label>
          </div>
          <div class="filler-area">
            <div style="font-size:13px;font-weight:500;color:var(--text);margin-bottom:6px;">Filler Words</div>
            <div style="font-size:12px;color:var(--text-3);margin-bottom:10px;">Words stripped when Auto Cleanup is on</div>
            <div class="filler-chips" id="filler-chips"></div>
            <div class="filler-add-row">
              <input class="filler-input" id="filler-input" placeholder="Add a word…"
                onkeydown="if(event.key===&quot;Enter&quot;)addFillerWord()">
              <button class="filler-add-btn" onclick="addFillerWord()">+ Add</button>
            </div>
          </div>
        </div>
      </div>

      <div class="settings-section">
        <div class="settings-title">Voice Commands</div>
        <div class="settings-card">
          <table class="cmd-table">
            <tr><td class="cmd-trigger">"new line"</td><td class="cmd-arrow">→</td><td class="cmd-desc">Inserts a newline</td></tr>
            <tr><td class="cmd-trigger">"new paragraph"</td><td class="cmd-arrow">→</td><td class="cmd-desc">Inserts two newlines</td></tr>
            <tr><td class="cmd-trigger">"period"</td><td class="cmd-arrow">→</td><td class="cmd-desc">Inserts .</td></tr>
            <tr><td class="cmd-trigger">"comma"</td><td class="cmd-arrow">→</td><td class="cmd-desc">Inserts ,</td></tr>
            <tr><td class="cmd-trigger">"question mark"</td><td class="cmd-arrow">→</td><td class="cmd-desc">Inserts ?</td></tr>
            <tr><td class="cmd-trigger">"exclamation mark"</td><td class="cmd-arrow">→</td><td class="cmd-desc">Inserts !</td></tr>
            <tr><td class="cmd-trigger">"clear that"</td><td class="cmd-arrow">→</td><td class="cmd-desc">Undo last paste (⌘Z)</td></tr>
            <tr><td class="cmd-trigger">"all caps"</td><td class="cmd-arrow">→</td><td class="cmd-desc">UPPERCASE next phrase</td></tr>
          </table>
        </div>
      </div>

      <div class="settings-section">
        <div class="settings-title">Data</div>
        <div class="settings-card">
          <div class="settings-row">
            <div>
              <div class="settings-row-label">Clear History</div>
              <div class="settings-row-sub">Remove all transcription history</div>
            </div>
            <button class="clear-btn" onclick="handleClear()">Clear all</button>
          </div>
        </div>
      </div>

      <div class="settings-section">
        <div class="settings-title">About</div>
        <div class="settings-card">
          <div class="settings-row">
            <div class="settings-row-label">VoiceType</div>
            <span style="font-size:13px;color:var(--text-3);">v__VERSION__</span>
          </div>
          <div class="settings-row">
            <div class="settings-row-label">Runs fully offline</div>
            <span style="font-size:13px;color:#22c55e;font-weight:600;">✓ Private</span>
          </div>
        </div>
      </div>
    </div>
  </div>

  <!-- Command toast notification -->
  <div class="cmd-toast" id="cmd-toast"></div>

</div>

<script>
var transcripts = [];
var totalWords = 0;
var currentState = "off";
var isEnabled = false;
var currentLang = "en";
var grammarResultText = "";
var currentTone = "fix";

var TONE_LABELS = {
  "fix":     "Fix Grammar →",
  "formal":  "Make Formal →",
  "casual":  "Make Casual →",
  "shorter": "Make Shorter →",
  "improve": "Improve →"
};

function setTone(tone, el) {
  currentTone = tone;
  document.querySelectorAll(".tone-btn").forEach(function(b) { b.classList.remove("active"); });
  el.classList.add("active");
  var btn = document.getElementById("grammar-fix-btn");
  if (btn) btn.textContent = TONE_LABELS[tone] || "Transform →";
}

function showPage(name) {
  document.querySelectorAll(".page").forEach(function(p) { p.classList.remove("active"); });
  document.querySelectorAll(".nav-item").forEach(function(n) { n.classList.remove("active"); });
  document.getElementById("page-" + name).classList.add("active");
  document.getElementById("nav-" + name).classList.add("active");
}

function handleToggle() {
  window.webkit.messageHandlers.voicetype.postMessage({action: "toggle", enabled: isEnabled});
}

function handleStop() {
  window.webkit.messageHandlers.voicetype.postMessage({action: "stop"});
}

function handleLanguage() {
  var sel = document.getElementById("lang-select");
  window.webkit.messageHandlers.voicetype.postMessage({action: "language", code: sel.value});
}

function handleModel() {
  var sel = document.getElementById("model-select");
  window.webkit.messageHandlers.voicetype.postMessage({action: "model", model_id: sel.value});
}

function handleClear() {
  transcripts = [];
  totalWords = 0;
  renderHistory();
  updateStats();
  window.webkit.messageHandlers.voicetype.postMessage({action: "clear"});
}

function handleCleanupToggle() {
  var cb = document.getElementById("cleanup-toggle");
  window.webkit.messageHandlers.voicetype.postMessage({action: "cleanup", enabled: cb.checked});
}

function handleGrammarAutoToggle() {
  var cb = document.getElementById("grammar-auto-toggle");
  window.webkit.messageHandlers.voicetype.postMessage({action: "grammar_auto", enabled: cb.checked});
}

function updateAiBadge(model) {
  var badge = document.getElementById("ai-badge");
  var sub   = document.getElementById("grammar-subtitle");
  if (model) {
    badge.textContent = "🤖 AI · " + model;
    badge.className = "ai-badge ai-on";
    badge.title = "Powered by Ollama · " + model;
    sub.textContent = "AI-powered · runs locally · fully private.";
  } else {
    badge.textContent = "⚡ Rule-based";
    badge.className = "ai-badge";
    badge.title = "Ollama not found — using built-in rules. Install Ollama for AI-powered fixes.";
    sub.textContent = "Select a tone, paste your text, and transform it — fully offline.";
  }
}

function handleGrammarFix() {
  var text = document.getElementById("grammar-input").value;
  if (!text.trim()) return;
  var btn   = document.getElementById("grammar-fix-btn");
  var badge = document.getElementById("ai-badge");
  var isAi  = badge.classList.contains("ai-on");
  btn.textContent = isAi ? "🤖 AI thinking…" : "Working…";
  btn.disabled = true;
  window.webkit.messageHandlers.voicetype.postMessage({action: "grammar", text: text, mode: currentTone});
}

function updateWordCount() {
  var text = document.getElementById("grammar-input").value;
  var words = text.trim() ? text.trim().split(/ +/).length : 0;
  document.getElementById("grammar-word-count").textContent = words + (words === 1 ? " word" : " words");
}

function showGrammarResult(correctedText, changeCount, aiModel) {
  var btn = document.getElementById("grammar-fix-btn");
  btn.textContent = TONE_LABELS[currentTone] || "Transform →";
  btn.disabled = false;

  // Update AI badge to reflect what was actually used this run
  updateAiBadge(aiModel || "");

  grammarResultText = correctedText;
  var original = document.getElementById("grammar-input").value;

  var outputEl = document.getElementById("grammar-output");
  outputEl.classList.remove("empty");

  var origWords = original.split(/ +/);
  var corrWords = correctedText.split(/ +/);
  var html = "";
  for (var i = 0; i < corrWords.length; i++) {
    var w = corrWords[i];
    var origW = origWords[i] || "";
    if (w !== origW) {
      html += '<span class="changed">' + escapeHtml(w) + '</span>';
    } else {
      html += escapeHtml(w);
    }
    if (i < corrWords.length - 1) html += " ";
  }
  outputEl.innerHTML = html;

  var badge = document.getElementById("grammar-change-badge");
  var copyBtn = document.getElementById("grammar-copy-btn");
  if (changeCount > 0) {
    badge.style.display = "";
    badge.textContent = changeCount + (changeCount === 1 ? " change" : " changes");
  } else {
    badge.style.display = "none";
  }
  copyBtn.style.display = "";
}

function copyGrammarResult() {
  if (!grammarResultText) return;
  var ta = document.createElement("textarea");
  ta.value = grammarResultText;
  document.body.appendChild(ta);
  ta.select();
  document.execCommand("copy");
  document.body.removeChild(ta);
  var btn = document.getElementById("grammar-copy-btn");
  btn.textContent = "Copied!";
  setTimeout(function(){ btn.textContent = "Copy"; }, 1500);
}

function updateWPM(wpm) {
  var el = document.getElementById("stat-wpm");
  if (el) el.textContent = wpm > 0 ? wpm : "—";
}

function updateStatus(state) {
  currentState = state;
  isEnabled = (state !== "off" && state !== "paused");
  var dot = document.getElementById("status-dot");
  var lbl = document.getElementById("status-label");
  var sub = document.getElementById("status-sub");
  var btn = document.getElementById("toggle-btn");
  var hero = document.getElementById("hero-title");
  var heroSub = document.getElementById("hero-sub");

  dot.className = "status-dot " + state;

  var map = {
    "off":          ["Off",           "Click Turn ON to start",                      "Turn ON",  "off",    "⏸  Off",              "Turn ON to start transcribing"],
    "paused":       ["Paused",        "Model loaded — resumes in under a second",    "▶ Resume", "resume", "⏸  Paused",           "Click Resume — no reload needed"],
    "loading":      ["Loading…",      "Warming up AI model (one-time)",              "⏸ Pause",  "on",     "Loading AI model…",   "Whisper is warming up, please wait"],
    "ready":        ["Ready",         "Hold Right ⌥ anywhere to speak",              "⏸ Pause",  "on",     "Hold Right ⌥",        "Speak anything — text pastes instantly"],
    "recording":    ["Recording…",    "Listening to your voice",                     "⏸ Pause",  "on",     "🔴 Recording…",       "Release Right ⌥ when done speaking"],
    "transcribing": ["Transcribing…", "Processing audio",                            "⏸ Pause",  "on",     "⏳ Transcribing…",    "Converting your speech to text"]
  };

  var info = map[state] || map["off"];
  lbl.textContent = info[0];
  sub.textContent = info[1];
  btn.textContent = info[2];
  btn.className = "toggle-btn " + info[3];
  hero.textContent = info[4];
  heroSub.textContent = info[5];

  var stopBtn = document.getElementById("stop-btn");
  if (stopBtn) {
    stopBtn.style.display = (state === "off") ? "none" : "";
  }
}

function addTranscription(text, timestamp) {
  var words = text.trim().split(" ").filter(function(w){return w.length>0;}).length;
  totalWords += words;
  transcripts.unshift({text: text, time: timestamp, words: words});
  if (transcripts.length > 50) transcripts = transcripts.slice(0, 50);
  renderHistory();
  updateStats();
}

function setLanguage(code) {
  currentLang = code;
  var sel = document.getElementById("lang-select");
  if (sel) sel.value = code;
  updateStats();
}

function calcTimeSaved(words) {
  var mins = words / 40;
  if (words === 0) return "—";
  if (mins < 1) {
    var s = Math.round(mins * 60);
    return s + "s";
  } else if (mins < 60) {
    var m = Math.floor(mins);
    var s2 = Math.round((mins - m) * 60);
    return s2 > 0 ? m + "m " + s2 + "s" : m + "m";
  } else {
    var h = Math.floor(mins / 60);
    var rm = Math.floor(mins % 60);
    return h + "h " + (rm > 0 ? rm + "m" : "");
  }
}

function updatePeriodStats(data) {
  var card = document.getElementById("time-saved-card");
  var periods = ["today","week","month","year"];
  var anyData = false;
  periods.forEach(function(p) {
    var words = (data && data[p]) ? data[p] : 0;
    var el = document.getElementById("ts-" + p);
    if (!el) return;
    if (words > 0) {
      el.textContent = calcTimeSaved(words);
      el.classList.remove("ts-zero");
      anyData = true;
    } else {
      el.textContent = "—";
      el.classList.add("ts-zero");
    }
  });
  if (card) {
    if (anyData) card.classList.add("has-data");
    else card.classList.remove("has-data");
  }
  var savedEl = document.getElementById("stat-saved");
  if (savedEl) {
    var todayWords = (data && data["today"]) ? data["today"] : 0;
    savedEl.textContent = todayWords > 0 ? calcTimeSaved(todayWords) : "—";
  }
  var wordsEl = document.getElementById("stat-words");
  if (wordsEl) {
    var todayWords2 = (data && data["today"]) ? data["today"] : 0;
    wordsEl.textContent = todayWords2.toLocaleString();
  }

  // By-month strip — one tile per calendar month that has data.
  var monthsWrap  = document.getElementById("ts-months-wrap");
  var monthsStrip = document.getElementById("ts-months-strip");
  var months = (data && data["months"]) ? data["months"] : [];
  if (monthsStrip && monthsWrap) {
    var withData = months.filter(function(m) { return m.words > 0; });
    if (withData.length > 0) {
      monthsStrip.innerHTML = withData.map(function(m) {
        return '<div class="ts-month">' +
                 '<div class="ts-month-value">' + calcTimeSaved(m.words) + '</div>' +
                 '<div class="ts-month-label">' + m.label + " " + m.year + '</div>' +
               '</div>';
      }).join("");
      monthsWrap.classList.add("has-months");
    } else {
      monthsStrip.innerHTML = "";
      monthsWrap.classList.remove("has-months");
    }
  }
}

function updateStats() {
  document.getElementById("stat-count").textContent = transcripts.length;
  var langMap = __LANG_MAP__;
  var name = langMap[currentLang] || "Auto";
  document.getElementById("stat-lang").textContent = name.toUpperCase().slice(0,2) || "AU";
}

function renderHistory() {
  var todayScroll = document.getElementById("today-scroll");
  var histScroll  = document.getElementById("history-scroll");

  var today = new Date().toDateString();
  var todayItems = transcripts.filter(function(h) {
    return new Date(h.time).toDateString() === today;
  });

  if (todayItems.length === 0) {
    todayScroll.innerHTML = '<div class="empty-state"><div class="empty-icon">🎙</div><div class="empty-title">No transcriptions yet</div><div class="empty-sub">Turn ON and hold Right ⌥ to speak</div></div>';
  } else {
    todayScroll.innerHTML = todayItems.map(function(item) {
      return '<div class="history-item"><div class="item-time">' + formatTime(item.time) + '</div><div class="item-text">' + escapeHtml(item.text) + '</div></div>';
    }).join("");
  }

  if (transcripts.length === 0) {
    histScroll.innerHTML = '<div class="empty-state"><div class="empty-icon">📋</div><div class="empty-title">No history yet</div><div class="empty-sub">Your transcriptions will appear here</div></div>';
  } else {
    var groups = {};
    var groupOrder = [];
    transcripts.forEach(function(item) {
      var d = new Date(item.time).toDateString();
      if (!groups[d]) { groups[d] = []; groupOrder.push(d); }
      groups[d].push(item);
    });
    histScroll.innerHTML = groupOrder.map(function(d) {
      var label = d === today ? "Today" : formatDate(new Date(d));
      var items = groups[d].map(function(item) {
        return '<div class="history-item"><div class="item-time">' + formatTime(item.time) + '</div><div class="item-text">' + escapeHtml(item.text) + '</div></div>';
      }).join("");
      return '<div class="date-group"><div class="date-label">' + label + '</div>' + items + '</div>';
    }).join("");
  }
}

function formatTime(ts) {
  var d = new Date(ts);
  var h = d.getHours(), m = d.getMinutes();
  var ampm = h >= 12 ? "PM" : "AM";
  h = h % 12 || 12;
  return h + ":" + (m < 10 ? "0" : "") + m + " " + ampm;
}

function formatDate(d) {
  var months = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
  return months[d.getMonth()] + " " + d.getDate() + ", " + d.getFullYear();
}

function escapeHtml(t) {
  return String(t == null ? "" : t).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;");
}

// ── Filler words ──────────────────────────────────────────────────────────
function renderFillerWords(words) {
  var chips = document.getElementById("filler-chips");
  if (!chips) return;
  if (!words || words.length === 0) {
    chips.innerHTML = '<span style="font-size:12px;color:var(--text-4);font-style:italic;">No filler words</span>';
    return;
  }
  chips.innerHTML = words.map(function(w) {
    var safe = escapeHtml(w);
    return '<div class="filler-chip">' + safe + '<span class="filler-chip-x" onclick="removeFillerWord(&quot;' + safe + '&quot;)">×</span></div>';
  }).join("");
}

function addFillerWord() {
  var inp = document.getElementById("filler-input");
  if (!inp) return;
  var word = inp.value.trim().toLowerCase();
  if (!word) return;
  inp.value = "";
  window.webkit.messageHandlers.voicetype.postMessage({action: "addFiller", word: word});
}

function removeFillerWord(word) {
  window.webkit.messageHandlers.voicetype.postMessage({action: "removeFiller", word: word});
}

// ── Command toast ─────────────────────────────────────────────────────────
function showCmdToast(label) {
  var t = document.getElementById("cmd-toast");
  if (!t) return;
  t.textContent = label;
  t.classList.add("visible");
  setTimeout(function() { t.classList.remove("visible"); }, 2000);
}

// ── Init ──────────────────────────────────────────────────────────────────
renderFillerWords(__FILLER_WORDS__);
</script>
</body>
</html>
"""


class _MessageHandler(NSObject):
    """Handles JS → Python messages from WKWebView."""

    def initWithDashboard_(self, dashboard):
        self = objc.super(_MessageHandler, self).init()
        if self is None:
            return None
        self._db = dashboard
        return self

    def userContentController_didReceiveScriptMessage_(self, controller, message):
        body = message.body()
        action = body.get("action")
        if action == "toggle":
            enabled = body.get("enabled", False)
            if self._db.on_toggle:
                self._db.on_toggle(not enabled)
        elif action == "stop":
            if self._db.on_stop:
                self._db.on_stop()
        elif action == "model":
            model_id = body.get("model_id", "")
            if model_id and self._db.on_model_change:
                self._db.on_model_change(model_id)
        elif action == "language":
            code = body.get("code", "en")
            self._db.current_lang = code
            if self._db.on_language_change:
                self._db.on_language_change(code)
        elif action == "clear":
            self._db.history = []
            self._db.count_today = 0
            self._db.total_words = 0
            today_str = datetime.date.today().isoformat()
            self._db._daily_stats.pop(today_str, None)
            try:
                _save_daily_stats(self._db._daily_stats)
            except Exception:
                pass
            period = _calc_period_words(self._db._daily_stats)
            self._db._js(f"updatePeriodStats({json.dumps(period)})")
        elif action == "cleanup":
            enabled = bool(body.get("enabled", False))
            self._db.auto_cleanup = enabled
            if self._db.on_settings_change:
                self._db.on_settings_change()
        elif action == "grammar_auto":
            enabled = bool(body.get("enabled", False))
            self._db.auto_grammar = enabled
        elif action == "grammar":
            text = body.get("text", "")
            mode = body.get("mode", "fix")
            threading.Thread(target=self._db._handle_grammar, args=(text, mode), daemon=True).start()
        elif action == "addFiller":
            word = body.get("word", "").strip().lower()
            if word and word not in self._db.filler_words:
                self._db.filler_words.append(word)
                _save_filler_words(self._db.filler_words)
                if self._db.on_filler_change:
                    self._db.on_filler_change(self._db.filler_words)
                self._db.refresh_filler_ui()
        elif action == "removeFiller":
            word = body.get("word", "").strip().lower()
            if word in self._db.filler_words:
                self._db.filler_words.remove(word)
                _save_filler_words(self._db.filler_words)
                if self._db.on_filler_change:
                    self._db.on_filler_change(self._db.filler_words)
                self._db.refresh_filler_ui()


class _WinDelegate(NSObject):
    def windowShouldClose_(self, window):
        window.orderOut_(None)
        return False


class _JSEvaluator(NSObject):
    """Helper that runs evaluateJavaScript on the main thread."""

    def initWithWebView_(self, webview):
        self = objc.super(_JSEvaluator, self).init()
        if self is None:
            return None
        self._webview = webview
        return self

    def evalScript_(self, script):
        self._webview.evaluateJavaScript_completionHandler_(script, None)


def _build_lang_options(current="en"):
    opts = []
    for name, code in LANGUAGES:
        sel = ' selected' if code == current else ''
        opts.append(f'<option value="{code}"{sel}>{name}</option>')
    return "\n".join(opts)


def _build_lang_map():
    pairs = []
    for name, code in LANGUAGES:
        key = code if code else "auto"
        pairs.append(f'"{key}": "{name}"')
    return "{" + ", ".join(pairs) + "}"


# ── Ollama local LLM ──────────────────────────────────────────────────────

_OLLAMA_BASE = "http://localhost:11434"
_OLLAMA_PREFERRED = [
    "phi3:mini", "phi3",
    "gemma2:2b", "gemma2",
    "llama3.2:1b", "llama3.2",
    "llama3:latest", "llama3",
    "mistral:latest", "mistral",
]

def _ollama_find_model():
    """Return the best available Ollama model name, or None if Ollama isn't running."""
    try:
        with urllib.request.urlopen(
            urllib.request.Request(_OLLAMA_BASE + "/api/tags"),
            timeout=2
        ) as resp:
            data = json.loads(resp.read())
            names = [m["name"] for m in data.get("models", [])]
            for pref in _OLLAMA_PREFERRED:
                root = pref.split(":")[0]
                for n in names:
                    if n.split(":")[0] == root:
                        return n
            return names[0] if names else None
    except Exception:
        return None

def _ollama_call(prompt, model):
    """POST to Ollama chat API. Returns response text or raises."""
    payload = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        "options": {"temperature": 0.2, "num_predict": 500},
    }).encode()
    req = urllib.request.Request(
        _OLLAMA_BASE + "/api/chat",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        result = json.loads(resp.read())
    text = result.get("message", {}).get("content", "").strip()
    # Strip common LLM preambles ("Here's the corrected text:", etc.)
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
    # Strip surrounding quotes the LLM sometimes adds
    if len(text) >= 2 and text[0] in ('"', "'") and text[-1] == text[0]:
        text = text[1:-1]
    return text.strip()

_OLLAMA_PROMPTS = {
    "fix": (
        "Fix the grammar, spelling and punctuation of the text below. "
        "Return ONLY the corrected text — no explanation, no quotes, no extra lines.\n\n{text}"
    ),
    "improve": (
        "Rewrite the text below to sound natural and fluent. "
        "Use contractions where natural, fix grammar, remove awkward phrasing, "
        "adjust tense for consistency. "
        "Return ONLY the rewritten text — no explanation, no quotes, no extra lines.\n\n{text}"
    ),
    "formal": (
        "Rewrite the text below in a formal, professional tone. "
        "Return ONLY the rewritten text — no explanation, no quotes, no extra lines.\n\n{text}"
    ),
    "casual": (
        "Rewrite the text below in a casual, friendly conversational tone. "
        "Return ONLY the rewritten text — no explanation, no quotes, no extra lines.\n\n{text}"
    ),
    "shorter": (
        "Make the text below more concise without losing its meaning. "
        "Return ONLY the shortened text — no explanation, no quotes, no extra lines.\n\n{text}"
    ),
}


class Dashboard:
    _instance = None

    @classmethod
    def get(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self):
        self.window         = None
        self._webview       = None
        self._handler       = None
        self._win_delegate  = None
        self._js_evaluator  = None

        self.history     = []
        self.count_today = 0
        self.total_words = 0
        self.is_enabled  = False
        self.current_lang = "en"

        # Persistent per-day word counts
        self._daily_stats = _load_daily_stats()
        _today = datetime.date.today().isoformat()
        self.total_words = self._daily_stats.get(_today, 0)

        # WPM tracking
        self.avg_wpm = 0
        self.wpm_samples = []

        # Toggles
        self.auto_cleanup = False
        self.auto_grammar = False

        # Filler words
        self.filler_words = _load_filler_words()

        # Callbacks
        self.on_toggle          = None
        self.on_stop            = None
        self.on_language_change = None
        self.on_model_change    = None
        self.on_settings_change = None
        self.on_filler_change   = None

    # ── Public API ────────────────────────────────────────────────────────

    def show(self):
        if self.window is None:
            self._build()
        AppKit.NSApp.activateIgnoringOtherApps_(True)
        self.window.makeKeyAndOrderFront_(None)
        # Refresh Ollama status badge every time the dashboard opens
        threading.Thread(target=self._push_ollama_status, daemon=True).start()

    def _push_ollama_status(self):
        model = _ollama_find_model()
        self._js(f"updateAiBadge({json.dumps(model or '')})")

    def update_status(self, state):
        self.is_enabled = (state != "off")
        self._js(f"updateStatus({json.dumps(state)})")

    def add_transcription(self, text):
        text = text.strip()
        if not text:
            return
        now = datetime.datetime.now().isoformat()
        words = len(text.split())
        self.total_words += words
        self.history.insert(0, {"text": text, "time": now})
        if len(self.history) > 50:
            self.history = self.history[:50]
        self.count_today += 1
        today_str = datetime.date.today().isoformat()
        self._daily_stats[today_str] = self._daily_stats.get(today_str, 0) + words
        try:
            _save_daily_stats(self._daily_stats)
        except Exception:
            pass
        period = _calc_period_words(self._daily_stats)
        self._js(f"addTranscription({json.dumps(text)}, {json.dumps(now)})")
        self._js(f"updatePeriodStats({json.dumps(period)})")

    def push_period_stats(self):
        """Push persisted period stats to JS (called after dashboard loads)."""
        period = _calc_period_words(self._daily_stats)
        self._js(f"updatePeriodStats({json.dumps(period)})")

    def set_language(self, code):
        self.current_lang = code
        self._js(f"setLanguage({json.dumps(code)})")

    def update_wpm(self, wpm):
        """Update rolling average WPM from last 20 samples, then push to UI."""
        self.wpm_samples.append(wpm)
        if len(self.wpm_samples) > 20:
            self.wpm_samples = self.wpm_samples[-20:]
        avg = int(round(sum(self.wpm_samples) / len(self.wpm_samples)))
        self.avg_wpm = avg
        self._js(f"updateWPM({avg})")

    def show_cmd_feedback(self, cmd):
        """Show brief toast for a voice command that just executed."""
        LABELS = {
            "newline":      "↵  New line",
            "newparagraph": "¶  New paragraph",
            "period":       ".  Period",
            "comma":        ",  Comma",
            "question":     "?  Question mark",
            "exclamation":  "!  Exclamation",
            "undo":         "⌘Z  Cleared",
            "allcaps":      "🔠  ALL CAPS next",
        }
        label = LABELS.get(cmd, cmd)
        self._js(f"showCmdToast({json.dumps(label)})")

    def refresh_filler_ui(self):
        self._js(f"renderFillerWords({json.dumps(self.filler_words)})")

    # ── Grammar fix ───────────────────────────────────────────────────────

    def _handle_grammar(self, text, mode="fix"):
        is_ai = False

        # ── Try Ollama first ──────────────────────────────────────────────
        model = _ollama_find_model()
        if model:
            try:
                prompt = _OLLAMA_PROMPTS.get(mode, _OLLAMA_PROMPTS["fix"]).format(text=text)
                corrected = _ollama_call(prompt, model)
                if corrected:
                    is_ai = True
            except Exception:
                corrected = None
        else:
            corrected = None

        # ── Fall back to rule-based ───────────────────────────────────────
        if not corrected:
            if mode == "formal":
                corrected = self._make_formal(text)
            elif mode == "casual":
                corrected = self._make_casual(text)
            elif mode == "shorter":
                corrected = self._make_shorter(text)
            elif mode == "improve":
                corrected = self._improve(text)
            else:
                corrected = self._fix_grammar(text)

        orig_words = text.split()
        corr_words = corrected.split()
        changes = sum(1 for a, b in zip(orig_words, corr_words) if a != b)
        changes += abs(len(orig_words) - len(corr_words))
        model_label = json.dumps(model if is_ai else "")
        self._js(f"showGrammarResult({json.dumps(corrected)}, {changes}, {model_label})")

    def _fix_grammar(self, text):
        if not text:
            return text

        def cap_sentence(m):
            return m.group(1) + m.group(2).upper()

        text = re.sub(r'([.!?]\s+)([a-z])', cap_sentence, text)
        if text and text[0].islower():
            text = text[0].upper() + text[1:]

        i_fixes = [
            (r"\bi'm\b", "I'm"),
            (r"\bi've\b", "I've"),
            (r"\bi'll\b", "I'll"),
            (r"\bi'd\b", "I'd"),
            (r"\bi\b", "I"),
        ]
        for pattern, replacement in i_fixes:
            text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)

        apostrophe_fixes = {
            r"\bwont\b": "won't",
            r"\bdont\b": "don't",
            r"\bcant\b": "can't",
            r"\bshouldnt\b": "shouldn't",
            r"\bwouldnt\b": "wouldn't",
            r"\bcouldnt\b": "couldn't",
            r"\bdidnt\b": "didn't",
            r"\bdoesnt\b": "doesn't",
            r"\bisnt\b": "isn't",
            r"\barent\b": "aren't",
            r"\bwerent\b": "weren't",
            r"\bwasnt\b": "wasn't",
            r"\bhasnt\b": "hasn't",
            r"\bhavent\b": "haven't",
            r"\bhadnt\b": "hadn't",
            r"\bwouldve\b": "would've",
            r"\bcouldve\b": "could've",
            r"\bshouldve\b": "should've",
            r"\bthats\b": "that's",
        }
        for pattern, replacement in apostrophe_fixes.items():
            text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)

        # Natural contractions — "do not" → "don't" etc.
        # These are the two-word forms that _fix_grammar previously missed entirely.
        contraction_fixes = [
            (r"\bI am\b",         "I'm"),
            (r"\bI have\b",       "I've"),
            (r"\bI will\b",       "I'll"),
            (r"\bI would\b",      "I'd"),
            (r"\bhe is\b",        "he's"),
            (r"\bshe is\b",       "she's"),
            (r"\bit is\b",        "it's"),
            (r"\bthat is\b",      "that's"),
            (r"\bthere is\b",     "there's"),
            (r"\bwhat is\b",      "what's"),
            (r"\bwho is\b",       "who's"),
            (r"\bthey are\b",     "they're"),
            (r"\bwe are\b",       "we're"),
            (r"\byou are\b",      "you're"),
            (r"\blet us\b",       "let's"),
            (r"\bdo not\b",       "don't"),
            (r"\bdoes not\b",     "doesn't"),
            (r"\bdid not\b",      "didn't"),
            (r"\bcannot\b",       "can't"),
            (r"\bwill not\b",     "won't"),
            (r"\bwould not\b",    "wouldn't"),
            (r"\bcould not\b",    "couldn't"),
            (r"\bshould not\b",   "shouldn't"),
            (r"\bis not\b",       "isn't"),
            (r"\bare not\b",      "aren't"),
            (r"\bwas not\b",      "wasn't"),
            (r"\bwere not\b",     "weren't"),
            (r"\bhas not\b",      "hasn't"),
            (r"\bhave not\b",     "haven't"),
            (r"\bhad not\b",      "hadn't"),
        ]
        for pattern, replacement in contraction_fixes:
            text = re.sub(pattern, replacement, text)

        text = re.sub(r'\s+([.,!?;:])', r'\1', text)
        text = re.sub(r'([.,!?;:])(?!\s|$)', r'\1 ', text)
        text = re.sub(r'  +', ' ', text)
        text = re.sub(r'\b(\w+)(\s+\1)+\b', r'\1', text, flags=re.IGNORECASE)

        def fix_article(m):
            article = m.group(1)
            space = m.group(2)
            word = m.group(3)
            if not word:
                return m.group(0)
            first_char = word[0].lower()
            if first_char in 'aeiou':
                correct = 'An' if article[0].isupper() else 'an'
            else:
                correct = 'A' if article[0].isupper() else 'a'
            return correct + space + word

        text = re.sub(r'\b(a|an)(\s+)(\w+)', fix_article, text, flags=re.IGNORECASE)

        # NSSpellChecker spelling corrections
        try:
            checker = AppKit.NSSpellChecker.sharedSpellChecker()
            corrected_words = []
            for token in text.split():
                leading  = re.match(r'^([^a-zA-Z]*)', token).group(1)
                trailing = re.search(r'([^a-zA-Z]*)$', token).group(1)
                core = token[len(leading): len(token) - len(trailing) if trailing else len(token)]
                if not core or not core[0].isalpha():
                    corrected_words.append(token)
                    continue
                rng, _ = checker.checkSpellingOfString_startingAt_language_wrap_inSpellDocumentWithTag_wordCount_(
                    core, 0, "en", False, 0, None
                )
                if rng.length > 0:
                    guesses = checker.guessesForWordRange_inString_language_inSpellDocumentWithTag_(
                        rng, core, "en", 0
                    )
                    if guesses:
                        suggestion = str(guesses[0])
                        if suggestion and suggestion != core and ' ' not in suggestion:
                            if core[0].isupper():
                                suggestion = suggestion[0].upper() + suggestion[1:]
                            corrected_words.append(leading + suggestion + trailing)
                            continue
                corrected_words.append(token)
            text = ' '.join(corrected_words)
        except Exception:
            pass

        return text.strip()

    # ── Shared helpers ────────────────────────────────────────────────────

    def _fix_double_comparatives(self, text):
        adj = (r"shorter|longer|bigger|smaller|faster|slower|higher|lower|"
               r"older|younger|stronger|weaker|harder|easier|heavier|lighter|"
               r"cheaper|cleaner|clearer|closer|cooler|darker|deeper|denser|"
               r"wider|thicker|thinner|louder|quieter|simpler|smarter|quicker")
        text = re.sub(rf"\bmore\s+({adj})\b", r"\1", text, flags=re.IGNORECASE)
        text = re.sub(r"\bless\s+(fewer|less)\b", r"\1", text, flags=re.IGNORECASE)
        return text

    def _strip_spoken_fillers(self, text):
        multi = [
            (r"\bI don'?t know,?\s*", ""),
            (r"\byou know,?\s*",       ""),
            (r"\bI mean,?\s*",         ""),
            (r"\bkind of\b",           ""),
            (r"\bsort of\b",           ""),
            (r"\bor something\b",      ""),
            (r"\bor whatever\b",       ""),
            (r"\band all\b",           ""),
            (r"\band stuff\b",         ""),
        ]
        single = [r"\blike\b", r"\bbasically\b", r"\bactually\b",
                  r"\bliterally\b", r"\bvery\b", r"\breally\b",
                  r"\bjust\b", r"\bsimply\b", r"\bquite\b",
                  r"\brather\b", r"\bsomewhat\b"]
        for pat, rep in multi:
            text = re.sub(pat, rep, text, flags=re.IGNORECASE)
        for pat in single:
            text = re.sub(pat, "", text, flags=re.IGNORECASE)
        return text

    def _tidy(self, text):
        text = re.sub(r'\b(\w+)(\s+\1)+\b', r'\1', text, flags=re.IGNORECASE)
        text = re.sub(r'\b((\w+\s+\w+))\s+\2\b', r'\1', text, flags=re.IGNORECASE)
        text = re.sub(r'\b((\w+\s+\w+\s+\w+))\s+\2\b', r'\1', text, flags=re.IGNORECASE)
        text = re.sub(r"  +", " ", text)
        text = re.sub(r"\s+([.,!?;:])", r"\1", text)
        text = re.sub(r"^[,;\s]+", "", text)
        text = text.strip()
        if text and text[0].islower():
            text = text[0].upper() + text[1:]
        return text

    # ── Tone transformations ──────────────────────────────────────────────

    def _make_formal(self, text):
        text = self._fix_grammar(text)
        text = self._fix_double_comparatives(text)
        text = self._strip_spoken_fillers(text)
        replacements = [
            (r"\bdon't\b",      "do not"),
            (r"\bcan't\b",      "cannot"),
            (r"\bwon't\b",      "will not"),
            (r"\bisn't\b",      "is not"),
            (r"\baren't\b",     "are not"),
            (r"\bwasn't\b",     "was not"),
            (r"\bweren't\b",    "were not"),
            (r"\bhasn't\b",     "has not"),
            (r"\bhaven't\b",    "have not"),
            (r"\bhadn't\b",     "had not"),
            (r"\bdidn't\b",     "did not"),
            (r"\bdoesn't\b",    "does not"),
            (r"\bshouldn't\b",  "should not"),
            (r"\bwouldn't\b",   "would not"),
            (r"\bcouldn't\b",   "could not"),
            (r"\bI'm\b",        "I am"),
            (r"\bI've\b",       "I have"),
            (r"\bI'll\b",       "I will"),
            (r"\bI'd\b",        "I would"),
            (r"\bit's\b",       "it is"),
            (r"\bthat's\b",     "that is"),
            (r"\bthere's\b",    "there is"),
            (r"\bthey're\b",    "they are"),
            (r"\bwe're\b",      "we are"),
            (r"\byou're\b",     "you are"),
            (r"\bhe's\b",       "he is"),
            (r"\bshe's\b",      "she is"),
            (r"\blet's\b",      "let us"),
            (r"\bwanna\b",      "want to"),
            (r"\bgonna\b",      "going to"),
            (r"\bgotta\b",      "have to"),
            (r"\bkinda\b",      "somewhat"),
            (r"\bsorta\b",      "somewhat"),
            (r"\byeah\b",       "yes"),
            (r"\bnope\b",       "no"),
            (r"\bokay\b",       "acceptable"),
            (r"\bok\b",         "acceptable"),
            (r"\bget\b",        "obtain"),
            (r"\bgot\b",        "obtained"),
            (r"\bshow\b",       "demonstrate"),
            (r"\buse\b",        "utilize"),
            (r"\bneed\b",       "require"),
            (r"\bhelp\b",       "assist"),
            (r"\bstart\b",      "commence"),
            (r"\bbuy\b",        "purchase"),
            (r"\bbig\b",        "significant"),
            (r"\bfix\b",        "rectify"),
            (r"\bcheck\b",      "verify"),
            (r"\blook at\b",    "review"),
            (r"\btry\b",        "attempt"),
        ]
        for pat, rep in replacements:
            text = re.sub(pat, rep, text)
        return self._tidy(text)

    def _make_casual(self, text):
        text = self._fix_grammar(text)
        replacements = [
            (r"\bdo not\b",       "don't"),
            (r"\bcannot\b",       "can't"),
            (r"\bwill not\b",     "won't"),
            (r"\bis not\b",       "isn't"),
            (r"\bare not\b",      "aren't"),
            (r"\bwas not\b",      "wasn't"),
            (r"\bwere not\b",     "weren't"),
            (r"\bhas not\b",      "hasn't"),
            (r"\bhave not\b",     "haven't"),
            (r"\bhad not\b",      "hadn't"),
            (r"\bdid not\b",      "didn't"),
            (r"\bdoes not\b",     "doesn't"),
            (r"\bshould not\b",   "shouldn't"),
            (r"\bwould not\b",    "wouldn't"),
            (r"\bcould not\b",    "couldn't"),
            (r"\bI am\b",         "I'm"),
            (r"\bI have\b",       "I've"),
            (r"\bI will\b",       "I'll"),
            (r"\bI would\b",      "I'd"),
            (r"\bit is\b",        "it's"),
            (r"\bthat is\b",      "that's"),
            (r"\bthere is\b",     "there's"),
            (r"\bthey are\b",     "they're"),
            (r"\bwe are\b",       "we're"),
            (r"\byou are\b",      "you're"),
            (r"\blet us\b",       "let's"),
            (r"\butilize\b",      "use"),
            (r"\bobtain\b",       "get"),
            (r"\bdemonstrate\b",  "show"),
            (r"\bsignificant\b",  "big"),
            (r"\bpurchase\b",     "buy"),
            (r"\brequire\b",      "need"),
            (r"\bassist\b",       "help"),
            (r"\bcommence\b",     "start"),
            (r"\brectify\b",      "fix"),
            (r"\bverify\b",       "check"),
            (r"\battempt\b",      "try"),
            (r"\bindividual\b",   "person"),
            (r"\bnevertheless\b", "still"),
            (r"\bfurthermore\b",  "also"),
            (r"\bhowever\b",      "but"),
            (r"\btherefore\b",    "so"),
            (r"\bsubsequently\b", "then"),
            (r"\bprior to\b",     "before"),
            (r"\bregarding\b",    "about"),
        ]
        for pat, rep in replacements:
            text = re.sub(pat, rep, text)
        return self._tidy(text)

    def _make_shorter(self, text):
        text = self._fix_grammar(text)
        text = self._fix_double_comparatives(text)
        text = self._strip_spoken_fillers(text)
        phrases = [
            (r"\bin order to\b",                    "to"),
            (r"\bdue to the fact that\b",           "because"),
            (r"\bat this point in time\b",          "now"),
            (r"\bat the present time\b",            "now"),
            (r"\bfor the purpose of\b",             "for"),
            (r"\bin the event that\b",              "if"),
            (r"\bwith regard to\b",                 "about"),
            (r"\bwith respect to\b",                "about"),
            (r"\bby means of\b",                    "by"),
            (r"\bit is important to note that\b",   ""),
            (r"\bplease be advised that\b",         ""),
            (r"\bit should be noted that\b",        ""),
            (r"\bthe fact that\b",                  "that"),
            (r"\ba large number of\b",              "many"),
            (r"\ba great deal of\b",                "much"),
            (r"\bon a daily basis\b",               "daily"),
            (r"\bon a regular basis\b",             "regularly"),
            (r"\bis able to\b",                     "can"),
            (r"\bare able to\b",                    "can"),
            (r"\bmake use of\b",                    "use"),
        ]
        for pat, rep in phrases:
            text = re.sub(pat, rep, text, flags=re.IGNORECASE)
        text = re.sub(r'\b(\w+)(\s+\1)+\b', r'\1', text, flags=re.IGNORECASE)
        return self._tidy(text)

    def _harmonize_tense(self, text):
        """
        When a sentence contains a past-tense anchor verb, shift present modals
        to their past forms so the whole sentence stays consistent.
        e.g. "I didn't know Claude can answer" → "I didn't know Claude could answer"
        """
        _PAST_ANCHOR = re.compile(
            r"\b(didn't|hadn't|wasn't|weren't|wouldn't|couldn't|shouldn't"
            r"|said|told|thought|knew|found|realised|realized|discovered"
            r"|heard|saw|noticed|expected|assumed|supposed|turned out)\b",
            re.IGNORECASE
        )
        if _PAST_ANCHOR.search(text):
            # can → could  (avoid "can't" — only standalone "can")
            text = re.sub(r"\bcan\b(?!'t)", "could", text)
            # will → would  (avoid "won't")
            text = re.sub(r"\bwill\b(?!'t)", "would", text)
            # may → might
            text = re.sub(r"\bmay\b", "might", text)
            # is → was  only after "that/who/which" clauses inside past context
            # (too aggressive to do broadly — skip)
        return text

    def _improve(self, text):
        text = self._fix_grammar(text)
        text = self._fix_double_comparatives(text)

        # ── High-frequency natural rewrites ──────────────────────────────
        natural = [
            # "do not have any idea" / "don't have any idea" → "have no idea"
            (r"\bdo(?:n't| not) have any idea\b",     "have no idea"),
            # "I am not sure that" → "I'm not sure"  (already contracted above)
            # "not able to" → "unable to"
            (r"\bnot able to\b",                      "unable to"),
            # "a lot of" → "many/much" when followed by plural/mass noun signal
            (r"\ba lot of\b",                         "many"),
            # "kind of" / "sort of" as hedges → remove
            (r"\bkind of\b",                          ""),
            (r"\bsort of\b",                          ""),
            # "for me personally" → "for me"
            (r"\bfor me personally\b",                "for me"),
            # "in my personal opinion" → "in my opinion"
            (r"\bin my personal opinion\b",           "in my opinion"),
            # "at the end of the day" → ""  (remove cliché)
            (r"\bat the end of the day[,]?\s*",       ""),
            # "the thing is" → ""
            (r"\bthe thing is[,]?\s*",                ""),
            # "what I mean is" → ""
            (r"\bwhat I mean is[,]?\s*",              ""),
        ]
        for pat, rep in natural:
            text = re.sub(pat, rep, text, flags=re.IGNORECASE)

        # Remove spoken-word fillers
        spoken = [
            (r"\byou know,?\s*",   ""),
            (r"\bI mean,?\s*",     ""),
            (r"\bbasically\b",     ""),
            (r"\bliterally\b",     ""),
        ]
        for pat, rep in spoken:
            text = re.sub(pat, rep, text, flags=re.IGNORECASE)

        # Remove optional "that" after common verbs
        # "I didn't know that Claude could" → "I didn't know Claude could"
        optional_that = [
            r"\b(know)\s+that\b",      r"\b(knew)\s+that\b",
            r"\b(think)\s+that\b",     r"\b(thought)\s+that\b",
            r"\b(feel)\s+that\b",      r"\b(felt)\s+that\b",
            r"\b(believe)\s+that\b",   r"\b(believed)\s+that\b",
            r"\b(say)\s+that\b",       r"\b(said)\s+that\b",
            r"\b(hope)\s+that\b",      r"\b(hoped)\s+that\b",
            r"\b(heard)\s+that\b",     r"\b(found)\s+that\b",
            r"\b(see)\s+that\b",       r"\b(saw)\s+that\b",
            r"\b(noticed)\s+that\b",   r"\b(assumed)\s+that\b",
            r"\b(realise|realize)\s+that\b",
            r"\b(understand)\s+that\b",
            r"\b(shows?)\s+that\b",    r"\b(means?)\s+that\b",
        ]
        for pat in optional_that:
            text = re.sub(pat, r"\1", text, flags=re.IGNORECASE)

        # Past-tense modal harmony — "didn't know Claude can" → "could"
        text = self._harmonize_tense(text)

        # Wordy → concise
        weak = [
            (r"\bis able to\b",             "can"),
            (r"\bare able to\b",            "can"),
            (r"\bwas able to\b",            "could"),
            (r"\bmake use of\b",            "use"),
            (r"\btake into account\b",      "consider"),
            (r"\bcome to an end\b",         "end"),
            (r"\bcarry out\b",              "do"),
            (r"\bput in place\b",           "implement"),
            (r"\bcome up with\b",           "develop"),
            (r"\bin order to\b",            "to"),
            (r"\bdue to the fact that\b",   "because"),
            (r"\bat this point in time\b",  "now"),
            (r"\bfor the purpose of\b",     "for"),
            (r"\bin the event that\b",      "if"),
            (r"\ba great deal of\b",        "much"),
            (r"\bon a regular basis\b",     "regularly"),
            (r"\bthe reason is because\b",  "because"),
            (r"\bfirst and foremost\b",     "first"),
            (r"\beach and every\b",         "every"),
        ]
        for pat, rep in weak:
            text = re.sub(pat, rep, text, flags=re.IGNORECASE)

        text = re.sub(r'\b(\w+)(\s+\1)+\b', r'\1', text, flags=re.IGNORECASE)
        return self._tidy(text)

    # ── Internal ──────────────────────────────────────────────────────────

    def _js(self, script):
        if self._webview is None or self._js_evaluator is None:
            return
        self._js_evaluator.performSelectorOnMainThread_withObject_waitUntilDone_(
            "evalScript:", script, False
        )

    def _build(self):
        W, H = 860, 580

        lang_options = _build_lang_options(self.current_lang)
        lang_map     = _build_lang_map()
        filler_json  = json.dumps(self.filler_words)
        html = (HTML_TEMPLATE
                .replace("__LANG_OPTIONS__", lang_options)
                .replace("__LANG_MAP__", lang_map)
                .replace("__FILLER_WORDS__", filler_json)
                .replace("__VERSION__", VERSION))

        self._handler = _MessageHandler.alloc().initWithDashboard_(self)
        controller    = WKUserContentController.alloc().init()
        controller.addScriptMessageHandler_name_(self._handler, "voicetype")

        config = WKWebViewConfiguration.alloc().init()
        config.setUserContentController_(controller)

        self._webview = WKWebView.alloc().initWithFrame_configuration_(
            NSMakeRect(0, 0, W, H), config
        )
        self._webview.loadHTMLString_baseURL_(html, None)
        self._js_evaluator = _JSEvaluator.alloc().initWithWebView_(self._webview)

        self._win_delegate = _WinDelegate.alloc().init()
        win = AppKit.NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            NSMakeRect(0, 0, W, H),
            (AppKit.NSWindowStyleMaskTitled |
             AppKit.NSWindowStyleMaskClosable |
             AppKit.NSWindowStyleMaskMiniaturizable |
             AppKit.NSWindowStyleMaskResizable),
            AppKit.NSBackingStoreBuffered,
            False,
        )
        win.setTitle_("VoiceType")
        win.setDelegate_(self._win_delegate)
        win.setContentView_(self._webview)
        win.setMinSize_(AppKit.NSMakeSize(680, 440))
        win.center()
        win.setReleasedWhenClosed_(False)
        self.window = win
