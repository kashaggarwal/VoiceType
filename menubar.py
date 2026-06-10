#!/usr/bin/env python3
"""
VoiceType Menu Bar — lives in your Mac menu bar.
"""

import os
import re
import subprocess
import threading
import time
import sys
from PIL import Image, ImageDraw
import pystray

try:
    import pyperclip as _pyperclip
except Exception:
    _pyperclip = None

# Hide Python icon from Dock
import AppKit
_app = AppKit.NSApplication.sharedApplication()
_app.setActivationPolicy_(1)

# Kill any orphaned worker from a previous session
try:
    subprocess.run(["pkill", "-f", "worker.py"], capture_output=True)
    time.sleep(0.3)
except Exception:
    pass

if getattr(sys, "frozen", False):
    _macos_dir = os.path.dirname(sys.executable)
    BASE_DIR   = sys._MEIPASS
    PYTHON     = None
    WORKER     = os.path.join(_macos_dir, "VoiceTypeWorker")
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    PYTHON   = os.path.join(BASE_DIR, "venv", "bin", "python")
    WORKER   = os.path.join(BASE_DIR, "worker.py")

from dashboard import Dashboard
_dash = Dashboard.get()

is_enabled    = False
is_paused     = False
worker        = None
icon_obj      = None
current_lang  = "en"
current_model = "mlx-community/whisper-small-mlx"
_last_state   = "off"


# ── Icon loading ──────────────────────────────────────────────────────────

def _load_icon(tint=None, alpha=1.0):
    icon_path = os.path.join(BASE_DIR, "icon.png")
    img = Image.open(icon_path).convert("RGBA")
    img = img.resize((64, 64), Image.LANCZOS)
    if tint is not None:
        r, g, b = tint
        pixels = img.load()
        for y in range(img.height):
            for x in range(img.width):
                pr, pg, pb, pa = pixels[x, y]
                if pa > 0:
                    lum = (pr + pg + pb) / 765.0
                    nr = int(r * lum * 1.4)
                    ng = int(g * lum * 1.4)
                    nb = int(b * lum * 1.4)
                    pixels[x, y] = (min(nr,255), min(ng,255), min(nb,255), int(pa * alpha))
    elif alpha < 1.0:
        pixels = img.load()
        for y in range(img.height):
            for x in range(img.width):
                pr, pg, pb, pa = pixels[x, y]
                pixels[x, y] = (pr, pg, pb, int(pa * alpha))
    return img

def _build_icons():
    return {
        "off":          _load_icon(alpha=0.45),
        "paused":       _load_icon(alpha=0.45),
        "loading":      _load_icon(tint=(255, 200, 0)),
        "ready":        _load_icon(),
        "recording":    _load_icon(tint=(231, 76, 60)),
        "transcribing": _load_icon(tint=(243, 156, 18)),
    }

_icons = {}


# ── HUD Overlay ───────────────────────────────────────────────────────────

class HUDOverlay:
    """
    Floating pill overlay — fixed width, dot+text centred as a group.
    Simple layout: measure text width, compute centre offset, place dot
    and label so the group sits in the middle of the pill. No attributed
    strings, no dynamic resizing, no paragraph style complexity.
    """

    W, H  = 148, 24   # fixed pill size (pt)
    DOT   = 6          # dot diameter
    GAP   = 5          # dot → text gap
    LBL_H = 14         # label frame height

    _FONT = None       # set in _build

    _STATES = {
        "loading":      ((1.00, 0.78, 0.00), "Loading model…"),
        "ready":        ((0.25, 0.83, 0.25), "Hold ⌥ to dictate"),
        "recording":    ((0.92, 0.28, 0.22), "Recording…"),
        "transcribing": ((0.95, 0.61, 0.07), "Transcribing…"),
    }

    def __init__(self):
        self._panel = None
        self._fx    = None
        self._dot   = None
        self._label = None
        self._build()

    # ── Construction ──────────────────────────────────────────────────────

    def _build(self):
        W, H = self.W, self.H
        HUDOverlay._FONT = AppKit.NSFont.systemFontOfSize_(11)

        scr     = AppKit.NSScreen.mainScreen().visibleFrame()  # excludes Dock
        x       = (scr.size.width - W) / 2
        y       = scr.origin.y + 8   # 8 pt gap above the Dock

        panel = AppKit.NSPanel.alloc().initWithContentRect_styleMask_backing_defer_(
            ((x, y), (W, H)), 0 | 128, AppKit.NSBackingStoreBuffered, False)
        panel.setLevel_(AppKit.NSFloatingWindowLevel)
        panel.setOpaque_(False)
        panel.setBackgroundColor_(AppKit.NSColor.clearColor())
        panel.setHasShadow_(True)
        panel.setMovableByWindowBackground_(True)
        panel.setCollectionBehavior_(1 | 16 | 64)

        cv = panel.contentView()

        fx = AppKit.NSVisualEffectView.alloc().initWithFrame_(((0, 0), (W, H)))
        fx.setMaterial_(6)       # HUDWindow — dark frosted glass
        fx.setBlendingMode_(0)
        fx.setState_(1)
        fx.setWantsLayer_(True)
        fx.layer().setCornerRadius_(H / 2)
        fx.layer().setMasksToBounds_(True)
        cv.addSubview_(fx)

        MID = H / 2

        # Dot — position updated in _apply
        dot = AppKit.NSView.alloc().initWithFrame_(
            ((0, MID - self.DOT / 2), (self.DOT, self.DOT))
        )
        dot.setWantsLayer_(True)
        dot.layer().setCornerRadius_(self.DOT / 2)
        dot.layer().setBackgroundColor_(AppKit.NSColor.systemGreenColor().CGColor())
        fx.addSubview_(dot)

        # Label — position updated in _apply
        lbl = AppKit.NSTextField.labelWithString_("")
        lbl.setFrame_(((0, MID - self.LBL_H / 2), (W, self.LBL_H)))
        lbl.setFont_(self._FONT)
        lbl.setTextColor_(AppKit.NSColor.labelColor())
        lbl.setWantsLayer_(True)
        fx.addSubview_(lbl)

        self._panel = panel
        self._fx    = fx
        self._dot   = dot
        self._label = lbl

    # ── Thread-safe public API ────────────────────────────────────────────

    def update(self, state):
        AppKit.NSOperationQueue.mainQueue().addOperationWithBlock_(
            lambda: self._apply(state)
        )

    # ── Main-thread update ────────────────────────────────────────────────

    def _apply(self, state):
        if state in ("off", "paused"):
            self._panel.orderOut_(None)
            return

        cfg = self._STATES.get(state)
        if cfg is None:
            return

        (r, g, b), text = cfg
        W, H   = self.W, self.H
        DOT    = self.DOT
        GAP    = self.GAP
        LBL_H  = self.LBL_H
        MID    = H / 2

        # Measure text width so we can centre the group precisely
        text_w = int(AppKit.NSString.stringWithString_(text).sizeWithAttributes_(
            {AppKit.NSFontAttributeName: self._FONT}
        ).width) + 2    # +2 px safety

        # Centre the [dot · gap · text] block in the pill
        group_w = DOT + GAP + text_w
        dot_x   = max(8, (W - group_w) / 2)   # never < 8 pt from edge
        lbl_x   = dot_x + DOT + GAP

        self._dot.setFrame_(((dot_x, MID - DOT / 2), (DOT, DOT)))
        self._label.setFrame_(((lbl_x, MID - LBL_H / 2), (text_w + 2, LBL_H)))
        self._label.setStringValue_(text)

        # Dot colour
        self._dot.layer().setBackgroundColor_(
            AppKit.NSColor.colorWithRed_green_blue_alpha_(r, g, b, 1.0).CGColor()
        )

        # Pulse dot while recording
        self._dot.layer().removeAllAnimations()
        if state == "recording":
            try:
                from Quartz import CABasicAnimation
                anim = CABasicAnimation.animationWithKeyPath_("opacity")
                anim.setFromValue_(1.0)
                anim.setToValue_(0.15)
                anim.setDuration_(0.65)
                anim.setAutoreverses_(True)
                anim.setRepeatCount_(999.0)
                self._dot.layer().addAnimation_forKey_(anim, "pulse")
            except Exception:
                pass

        if not self._panel.isVisible():
            self._panel.orderFront_(None)


_hud = None


# ── Icon state ────────────────────────────────────────────────────────────

def set_icon_state(state):
    global _last_state
    _last_state = state
    if icon_obj is None:
        return
    TITLES = {
        "off":          "VoiceType — Off",
        "paused":       "VoiceType — Paused",
        "loading":      "VoiceType — Loading…",
        "ready":        "VoiceType — Listening (hold Right ⌥)",
        "recording":    "VoiceType — Recording…",
        "transcribing": "VoiceType — Transcribing…",
    }
    icon_obj.icon  = _icons.get(state, _icons["off"])
    icon_obj.title = TITLES.get(state, "VoiceType")
    threading.Thread(target=_dash.update_status, args=(state,), daemon=True).start()
    if _hud:
        _hud.update(state)


# ── Worker control ────────────────────────────────────────────────────────

def _send_to_worker(msg: str):
    global worker
    if worker and worker.stdin:
        try:
            worker.stdin.write((msg + "\n").encode())
            worker.stdin.flush()
        except Exception:
            pass

def _start_worker(lang=None, model=None):
    global is_enabled, is_paused, worker, current_lang, current_model
    is_enabled = True
    is_paused  = False
    if lang:
        current_lang = lang
    if model:
        current_model = model
    set_icon_state("loading")

    cmd = [PYTHON, WORKER] if not getattr(sys, "frozen", False) else [WORKER]
    if current_lang:
        cmd += ["--lang", current_lang]
    if current_model:
        cmd += ["--model", current_model]
    if _dash.auto_cleanup:
        cmd += ["--cleanup"]

    try:
        worker = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=open("/tmp/vt_worker_stderr.log", "w"),
            stdin=subprocess.PIPE,
        )
        with open("/tmp/vt_menu.log", "a") as f:
            f.write(f"Worker spawned PID={worker.pid} lang={current_lang}\n")
    except Exception:
        import traceback as _tb
        with open("/tmp/vt_menu.log", "a") as f:
            f.write(_tb.format_exc())
        is_enabled = False
        return

    filler_str = ",".join(_dash.filler_words)
    if filler_str:
        _send_to_worker(f"filler:{filler_str}")

    threading.Thread(target=_monitor_worker, daemon=True).start()

def _pause_worker():
    global is_paused
    if not is_enabled or not worker:
        return
    is_paused = True
    _send_to_worker("pause")
    set_icon_state("paused")

def _resume_worker():
    global is_paused
    if not is_enabled or not worker:
        return
    is_paused = False
    _send_to_worker("resume")

def _kill_worker():
    global is_enabled, is_paused, worker
    is_enabled = False
    is_paused  = False
    set_icon_state("off")
    if worker:
        worker.terminate()
        worker = None

def _restart_with_lang(lang_code):
    global current_lang
    current_lang = lang_code
    if is_enabled:
        _kill_worker()
        time.sleep(0.3)
        _start_worker(lang=lang_code)

def _restart_with_model(model_id):
    global current_model
    current_model = model_id
    if is_enabled:
        _kill_worker()
        time.sleep(0.3)
        _start_worker(model=model_id)

def _restart_worker():
    if is_enabled:
        _kill_worker()
        time.sleep(0.3)
        _start_worker()

def _on_filler_change(words):
    if is_enabled and not is_paused:
        _send_to_worker("filler:" + ",".join(words))


# ── Post-paste grammar fix ────────────────────────────────────────────────

def _try_paste():
    try:
        import Quartz as Q
        src  = Q.CGEventSourceCreate(Q.kCGEventSourceStateHIDSystemState)
        v_dn = Q.CGEventCreateKeyboardEvent(src, 0x09, True)
        v_up = Q.CGEventCreateKeyboardEvent(src, 0x09, False)
        Q.CGEventSetFlags(v_dn, Q.kCGEventFlagMaskCommand)
        Q.CGEventSetFlags(v_up, Q.kCGEventFlagMaskCommand)
        Q.CGEventPost(Q.kCGHIDEventTap, v_dn)
        Q.CGEventPost(Q.kCGHIDEventTap, v_up)
    except Exception:
        subprocess.run([
            "osascript", "-e",
            'tell application "System Events" to keystroke "v" using command down'
        ])

def _apply_grammar_fix(raw_text):
    """After worker already pasted raw_text, replace with grammar-fixed version."""
    try:
        corrected = _dash._fix_grammar(raw_text)
        if corrected and corrected != raw_text and _pyperclip:
            time.sleep(0.15)
            _pyperclip.copy(corrected)
            # Undo the raw paste, then paste corrected
            try:
                import Quartz as Q
                src = Q.CGEventSourceCreate(Q.kCGEventSourceStateHIDSystemState)
                dn = Q.CGEventCreateKeyboardEvent(src, 0x06, True)
                up = Q.CGEventCreateKeyboardEvent(src, 0x06, False)
                Q.CGEventSetFlags(dn, Q.kCGEventFlagMaskCommand)
                Q.CGEventSetFlags(up, Q.kCGEventFlagMaskCommand)
                Q.CGEventPost(Q.kCGHIDEventTap, dn)
                time.sleep(0.02)
                Q.CGEventPost(Q.kCGHIDEventTap, up)
            except Exception:
                pass
            time.sleep(0.06)
            _try_paste()
            return corrected
    except Exception:
        pass
    return raw_text


# ── Monitor worker stdout ─────────────────────────────────────────────────

def _monitor_worker():
    global worker
    for raw in worker.stdout:
        if not is_enabled:
            break
        line = raw.decode().strip()
        if line.startswith("text:"):
            raw_text = line[5:]
            # Worker already pasted. Apply grammar fix if enabled.
            if _dash.auto_grammar and raw_text:
                final = _apply_grammar_fix(raw_text)
            else:
                final = raw_text
            _dash.add_transcription(final)
        elif line.startswith("wpm:"):
            try:
                _dash.update_wpm(int(line[4:]))
            except ValueError:
                pass
        elif line.startswith("cmd:"):
            threading.Thread(
                target=_dash.show_cmd_feedback, args=(line[4:],), daemon=True
            ).start()
        elif line == "paused":
            set_icon_state("paused")
        else:
            set_icon_state(line)


# ── Menu actions ──────────────────────────────────────────────────────────

def _enable():
    if is_enabled and is_paused:
        _resume_worker()
    elif not is_enabled:
        _start_worker()

def _disable():
    if is_enabled and not is_paused:
        _pause_worker()

def toggle(icon, item):
    if not is_enabled or is_paused:
        _enable()
    else:
        _disable()

def open_dashboard(icon, item):
    _dash.show()
    def _sync_state():
        time.sleep(0.8)
        _dash.update_status(_last_state)
        _dash.set_language(current_lang)
        _dash.push_period_stats()
    threading.Thread(target=_sync_state, daemon=True).start()

def get_toggle_label(item):
    return "Turn OFF" if (is_enabled and not is_paused) else "Turn ON"

def quit_app(icon, item):
    _kill_worker()
    icon.stop()


# ── Wire dashboard callbacks ──────────────────────────────────────────────

def _dash_toggle(enable):
    if enable:
        _enable()
    else:
        _disable()

_dash.on_toggle          = _dash_toggle
_dash.on_stop            = _kill_worker
_dash.on_language_change = _restart_with_lang
_dash.on_model_change    = _restart_with_model
_dash.on_settings_change = _restart_worker
_dash.on_filler_change   = _on_filler_change
_dash.on_config_change   = lambda: _send_to_worker("reload_config")


# ── Edit menu ─────────────────────────────────────────────────────────────

def _install_edit_menu():
    main_menu = AppKit.NSMenu.alloc().init()
    edit_item = AppKit.NSMenuItem.alloc().init()
    edit_menu = AppKit.NSMenu.alloc().initWithTitle_("Edit")

    def _item(title, action, key, shift=False):
        it = AppKit.NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            title, action, key
        )
        if shift:
            it.setKeyEquivalentModifierMask_(
                AppKit.NSEventModifierFlagCommand | AppKit.NSEventModifierFlagShift
            )
        return it

    edit_menu.addItem_(_item("Undo",       "undo:",      "z"))
    edit_menu.addItem_(_item("Redo",       "redo:",      "z", shift=True))
    edit_menu.addItem_(AppKit.NSMenuItem.separatorItem())
    edit_menu.addItem_(_item("Cut",        "cut:",       "x"))
    edit_menu.addItem_(_item("Copy",       "copy:",      "c"))
    edit_menu.addItem_(_item("Paste",      "paste:",     "v"))
    edit_menu.addItem_(_item("Select All", "selectAll:", "a"))

    edit_item.setSubmenu_(edit_menu)
    main_menu.addItem_(edit_item)
    AppKit.NSApp.setMainMenu_(main_menu)


# ── Main ──────────────────────────────────────────────────────────────────

def main():
    global icon_obj, _icons, _hud
    _install_edit_menu()
    _icons = _build_icons()
    _hud = HUDOverlay()
    menu = pystray.Menu(
        pystray.MenuItem(get_toggle_label, toggle, default=True),
        pystray.MenuItem("Open Dashboard", open_dashboard),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Quit VoiceType", quit_app),
    )
    icon_obj = pystray.Icon(
        "VoiceType",
        _icons["off"],
        "VoiceType — Off",
        menu=menu,
    )
    print("VoiceType running — look for the icon in your menu bar", flush=True)
    icon_obj.run()

if __name__ == "__main__":
    main()
