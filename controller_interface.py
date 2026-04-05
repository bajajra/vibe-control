"""
Vibe Control — PlayStation controller interface for macOS
Maps joysticks to mouse/scroll, buttons to IDE shortcuts, R1 to dictation.
"""

import os
import sys
import time
import math
import json
import logging
import subprocess

import pygame
import pyautogui

from dictation import DictationHandler
from defaults import DEFAULT_CONFIG, deep_merge
from dualsense_rumble import DualSenseRumble, detect_hid_bt
from prompt_detect import approval_prompt_active
from ui_draw import (
    COL_ACCENT,
    COL_ACCENT_GLOW,
    COL_BORDER,
    COL_BORDER_SUBTLE,
    COL_BG_TOP,
    COL_BG_BOT,
    COL_DANGER,
    COL_SUCCESS,
    COL_SURFACE,
    COL_SURFACE_HOVER,
    COL_SURFACE_RAISED,
    COL_TEXT,
    COL_TEXT_MUTED,
    COL_TEXT_DIM,
    draw_card,
    draw_chip,
    draw_frosted_panel,
    draw_glow_circle,
    draw_inner_glow,
    draw_pill,
    draw_rounded_rect,
    draw_rounded_rect_alpha,
    draw_search_bar,
    draw_shadow,
    draw_soft_divider,
    draw_vertical_gradient,
)
from keymap import chord_from_event, format_chord

pyautogui.PAUSE = 0
pyautogui.FAILSAFE = True  # move mouse to top-left corner to abort

# ── Debug log ──────────────────────────────────────────────────────
log = logging.getLogger("vibecontrol")
log.setLevel(logging.DEBUG)
_fh = logging.FileHandler(os.path.expanduser("~/vibecontrol.log"))
_fh.setFormatter(logging.Formatter("%(asctime)s  %(levelname)-5s  %(message)s"))
log.addHandler(_fh)

SPEED_LABELS = ["SLOW", "MEDIUM", "FAST"]

MOUSE_ACTIONS = frozenset({"left_click", "right_click", "double_click"})

# Row height for the bindings list (controller + action + chord)
BIND_ROW_H = 52

# Supported dictation languages (label, BCP-47 code)
DICTATION_LANGUAGES = [
    ("English (US)", "en-US"),
    ("English (UK)", "en-GB"),
    ("Chinese (Simplified)", "zh-CN"),
    ("Chinese (Traditional)", "zh-TW"),
    ("Cantonese", "zh-HK"),
    ("Hindi", "hi-IN"),
    ("Spanish", "es-ES"),
    ("French", "fr-FR"),
    ("German", "de-DE"),
    ("Japanese", "ja-JP"),
    ("Korean", "ko-KR"),
    ("Portuguese (BR)", "pt-BR"),
]

# Map config button keys to on-screen DualSense labels
_PHYSICAL_BTN_LABEL = {
    "cross": "X",
    "circle": "O",
    "square": "Sq",
    "triangle": "Tr",
    "l1": "L1",
    "r1": "R1",
    "l3": "L3",
    "r3": "R3",
    "l2_trigger": "L2",
    "r2_trigger": "R2 (full pull)",
    "touchpad": "Touchpad",
    "options": "Options",
    "share": "Share / Create",
    "ps": "PS",
    "dpad_up": "D-pad Up",
    "dpad_down": "D-pad Down",
    "dpad_left": "D-pad Left",
    "dpad_right": "D-pad Right",
}

# Scrollable binding reference (Options+Share opens overlay). Lines starting with ">> " are section titles.
_GUIDE_LINES = [
    ">> Open / close this guide",
    "Options + Share - show or hide (works even if controller is paused)",
    "While open: O / PS / Options+Share / Esc - close, right stick or mouse wheel - scroll",
    "",
    ">> Sticks & triggers",
    "Left stick - mouse (normal), arrow keys (hold L1 code mode)",
    "Right stick - scroll in the focused app (not while this guide is open)",
    "L2 hold - slow / precision mouse",
    "R2 full pull - Enter (same action as in config for normal / code)",
    "",
    ">> Global chords (any time, even when paused)",
    "L2 + X (Cross) - Enter / Run in prompts",
    "L2 + O (Circle) - Escape",
    "",
    ">> Normal mode (L1 released)",
    "X - left click    O - backspace    Sq - copy    Tr - paste",
    "L3 - right click    R3 - cycle mouse speed",
    "D-pad - arrow keys    Options - command palette    Share - save",
    "Touchpad - AI chat + dictate + paste + Enter",
    "R1 hold - voice dictation (release to transcribe & paste)",
    "PS - pause / resume controller (mouse & shortcuts)",
    "L2 + D-pad Left/Right - prev / next window (same app)",
    "L2 + D-pad Up/Down - tmux / screen prev & next window",
    "",
    ">> Code mode (hold L1)",
    "Left stick - navigate code with arrows",
    "X - go to definition    O - delete word    Sq - find    Tr - terminal",
    "D-pad - quick open / symbol / prev tab / next tab",
    "Options - AI chat    Share - Ctrl+C interrupt    Touchpad - app switcher",
    "L3 - undo    R3 - Escape",
    "",
    ">> App window",
    "Dashboard - live status    Bindings - DualSense > keyboard (edit chords)",
    "Bindings: select row, Enter, then type new shortcut",
]
_GUIDE_LINE_H = 20

ACTION_LABELS = {
    "left_click": "Left click",
    "right_click": "Right click",
    "double_click": "Double click",
    "copy": "Copy",
    "paste": "Paste",
    "cut": "Cut",
    "undo": "Undo",
    "redo": "Redo",
    "save_file": "Save file",
    "find": "Find",
    "command_palette": "Command palette",
    "quick_open": "Quick open",
    "go_to_symbol": "Go to symbol",
    "go_to_definition": "Go to definition",
    "go_back": "Go back",
    "prev_tab": "Previous tab",
    "next_tab": "Next tab",
    "toggle_terminal": "Toggle terminal",
    "ai_chat": "AI chat",
    "ai_edit": "AI inline edit",
    "ai_composer": "AI composer",
    "escape": "Escape",
    "enter": "Enter / Return",
    "tab": "Tab",
    "arrow_up": "Arrow up",
    "arrow_down": "Arrow down",
    "arrow_left": "Arrow left",
    "arrow_right": "Arrow right",
    "select_all": "Select all",
    "close_tab": "Close tab",
    "backspace": "Backspace",
    "word_backspace": "Delete word",
    "interrupt": "Interrupt (Ctrl+C)",
    "app_switch": "App switcher",
    "next_app_window": "Next window (same app, Cmd+`)",
    "prev_app_window": "Previous window (same app, Cmd+Shift+`)",
    "mux_next_window": "Tmux next window (Ctrl+b n)",
    "mux_prev_window": "Tmux previous window (Ctrl+b p)",
    "next_pane": "Next pane (Cmd+])",
    "prev_pane": "Previous pane (Cmd+[)",
}

# Keyboard shortcut definitions used by action handlers.
# Keys are pyautogui key names; tuples become hotkey() args, strings become press() args.
SHORTCUTS = {
    "left_click":       ("click",),
    "right_click":      ("rightClick",),
    "double_click":     ("doubleClick",),
    "copy":             ("command", "c"),
    "paste":            ("command", "v"),
    "cut":              ("command", "x"),
    "undo":             ("command", "z"),
    "redo":             ("command", "shift", "z"),
    "save_file":        ("command", "s"),
    "find":             ("command", "f"),
    "command_palette":  ("command", "shift", "p"),
    "quick_open":       ("command", "p"),
    "go_to_symbol":     ("command", "shift", "o"),
    "go_to_definition": ("f12",),
    "go_back":          ("control", "-"),
    "prev_tab":         ("command", "shift", "["),
    "next_tab":         ("command", "shift", "]"),
    "toggle_terminal":  ("control", "`"),
    "ai_chat":          ("command", "l"),
    "ai_edit":          ("command", "k"),
    "ai_composer":      ("command", "i"),
    "escape":           ("escape",),
    "enter":            ("return",),
    "tab":              ("tab",),
    "arrow_up":         ("up",),
    "arrow_down":       ("down",),
    "arrow_left":       ("left",),
    "arrow_right":      ("right",),
    "select_all":       ("command", "a"),
    "close_tab":        ("command", "w"),
    "backspace":        ("backspace",),
    "word_backspace":   ("option", "backspace"),
    "interrupt":        ("control", "c"),
    "app_switch":       ("command", "tab"),
    "next_app_window":  ("command", "`"),
    "prev_app_window":  ("command", "shift", "`"),
    "next_pane":        ("command", "]"),
    "prev_pane":        ("command", "["),
}


class ControllerInterface:

    def __init__(self, config_path="config.json", sensitivity=1.0, discover=False):
        self.config_path = config_path
        self.cfg = self._load_config(config_path)
        self.sensitivity = sensitivity
        self.discover = discover

        # --- state ---
        self.running = True
        self.active = True
        self.l1_held = False
        self.mode = "NORMAL"
        self.dictation_status = "IDLE"
        self._dictation_send_after = False  # press Enter after pasting (for AI chat)

        # mouse
        mcfg = self.cfg.get("mouse", {})
        self.deadzone = mcfg.get("deadzone", 0.15)
        self.accel = mcfg.get("acceleration_curve", 2.0)
        self.speeds = mcfg.get("speeds", [5, 15, 35])
        self.speed_idx = mcfg.get("default_speed_level", 1)

        # scroll
        scfg = self.cfg.get("scroll", {})
        self.scroll_v = scfg.get("vertical_speed", 3)
        self.scroll_h = scfg.get("horizontal_speed", 3)
        self.scroll_dz = scfg.get("deadzone", 0.25)
        self.scroll_throttle = scfg.get("throttle_ms", 30)

        # button / axis indices (DualSense with 17 buttons, D-pad as buttons 11-14)
        self.btn = {
            "cross": 0, "circle": 1, "square": 2, "triangle": 3,
            "share": 4, "ps": 5, "options": 6,
            "l3": 7, "r3": 8, "l1": 9, "r1": 10,
            "dpad_up": 11, "dpad_down": 12, "dpad_left": 13, "dpad_right": 14,
            "touchpad": 15,
        }
        self.btn.update(self.cfg.get("button_indices", {}))
        self.btn_rev = {v: k for k, v in self.btn.items()}

        self.ax = {
            "left_x": 0, "left_y": 1, "right_x": 2, "right_y": 3,
            "l2_trigger": 4, "r2_trigger": 5,
        }
        self.ax.update(self.cfg.get("axis_indices", {}))

        # action maps from config (action name strings)
        self.normal_actions = self.cfg.get("normal_mode", {})
        self.code_actions = self.cfg.get("code_mode", {})

        self.shortcuts = {}
        self._rebuild_shortcuts()
        self._refresh_bind_actions()

        # throttle timestamps
        self._ts = {}

        # dpad hat state
        self._dpad = {"up": False, "down": False, "left": False, "right": False}

        # dictation
        dcfg = self.cfg.get("dictation", {})
        self.dictation = DictationHandler(
            engine=dcfg.get("engine", "google"),
            language=dcfg.get("language", "en-US"),
            corrections=dcfg.get("corrections", {}),
        )
        self.dictation.set_callbacks(
            on_transcription=self._on_text,
            on_status=self._on_dict_status,
        )

        # vibration
        vcfg = self.cfg.get("vibration", {})
        self.vib_enabled = vcfg.get("enabled", True)
        self.vib_on_startup = vcfg.get("on_startup", True)
        self.vib_on_dictation = vcfg.get("on_dictation", True)
        self.vib_on_mode_change = vcfg.get("on_mode_change", True)
        self.vib_on_approval_prompt = vcfg.get("on_approval_prompt", True)
        self.approval_scan_interval_s = vcfg.get("approval_prompt_scan_ms", 300) / 1000.0
        self.approval_pulse_interval_s = vcfg.get("approval_prompt_pulse_ms", 520) / 1000.0
        self._approval_scan_t = 0.0
        self._approval_pulse_t = 0.0
        self._approval_prompt_active = False
        self._approval_pulse_phase = False

        # Track the joystick instance_id so we can tell real disconnects
        # from SDL's spurious JOYDEVICEADDED at startup.
        self._js_instance_id = None
        self._init_time = None

        # UI state (Shortcuts editor + Raycast-style chrome)
        self.ui_panel = "dashboard"
        self._bind_scroll = 0
        self._bind_selected_idx = -1
        self._bind_recording_action = None
        self._tab_dash_r = pygame.Rect(0, 0, 0, 0)
        self._tab_bind_r = pygame.Rect(0, 0, 0, 0)
        self._tab_dict_r = pygame.Rect(0, 0, 0, 0)
        self._bind_rows = []
        self._mouse_chip_rects = []
        self._mode_chip_r = pygame.Rect(0, 0, 0, 0)
        self._speed_chip_r = pygame.Rect(0, 0, 0, 0)
        self._lang_chip_r = pygame.Rect(0, 0, 0, 0)
        self._lang_dropdown_open = False
        self._lang_dropdown_rects = []  # list of (pygame.Rect, lang_code)
        self._lang_dropdown_scroll = 0
        self._lang_dropdown_panel = pygame.Rect(0, 0, 0, 0)
        self.guide_overlay = False
        self.guide_scroll = 0
        self._guide_close_r = pygame.Rect(0, 0, 0, 0)

        # Dictation corrections tab state
        self._dict_scroll = 0
        self._dict_selected_idx = -1
        self._dict_editing = None       # None | "pattern" | "replacement"
        self._dict_edit_buf = ""
        self._dict_adding = False        # True when adding a new entry
        self._dict_add_pattern = ""
        self._dict_add_replacement = ""
        self._dict_add_field = "pattern"  # which field is active: "pattern" | "replacement"
        self._dict_rows = []
        self._dict_add_btn_r = pygame.Rect(0, 0, 0, 0)

        self._init_pygame()
        self._init_joystick()

    # ------------------------------------------------------------------ init

    @staticmethod
    def _load_config(path):
        loaded = {}
        try:
            with open(path) as f:
                loaded = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            pass
        return deep_merge(DEFAULT_CONFIG, loaded)

    def _rebuild_shortcuts(self):
        self.shortcuts = dict(SHORTCUTS)
        ov = self.cfg.get("shortcut_overrides", {})
        for k, v in ov.items():
            if isinstance(v, (list, tuple)) and len(v) > 0:
                self.shortcuts[k] = tuple(v)

    def _refresh_bind_actions(self):
        seen = set()
        for m in (self.normal_actions, self.code_actions):
            for v in m.values():
                if v in ("speak_to_ai", "cycle_speed"):
                    continue
                if v in self.shortcuts:
                    seen.add(v)
        for aid in ("next_app_window", "prev_app_window"):
            if aid in self.shortcuts:
                seen.add(aid)
        self._bind_action_ids = sorted(seen, key=lambda x: ACTION_LABELS.get(x, x).lower())

    def _physical_btn(self, btn_key: str) -> str:
        return _PHYSICAL_BTN_LABEL.get(btn_key, btn_key.replace("_", " "))

    def _controller_combo_summary(self, aid: str) -> str:
        """Human-readable DualSense combos that trigger this action (keyboard chord is separate)."""
        pieces: list[str] = []
        seen: set[str] = set()

        def add(s: str) -> None:
            if s not in seen:
                seen.add(s)
                pieces.append(s)

        orphan_ctrl = {
            "next_app_window": "Normal - L2 + D-pad Right",
            "prev_app_window": "Normal - L2 + D-pad Left",
        }
        if aid in orphan_ctrl:
            add(orphan_ctrl[aid])
        for btn, act in self.normal_actions.items():
            if act == aid:
                add(f"Normal - {self._physical_btn(btn)}")
        for btn, act in self.code_actions.items():
            if act == aid:
                add(f"L1 - {self._physical_btn(btn)}")
        if aid == "enter":
            add("L2 + X (any time)")
        if aid == "escape":
            add("L2 + O (any time)")
        if not pieces:
            return "--"
        return "    ".join(pieces)

    @staticmethod
    def _truncate_to_width(font, text: str, max_w: int) -> str:
        if max_w <= 10 or not text:
            return text
        if font.size(text)[0] <= max_w:
            return text
        ell = "..."
        t = text
        while t and font.size(t + ell)[0] > max_w:
            t = t[:-1]
        return t + ell if t else ell

    def _save_config(self):
        try:
            with open(self.config_path, "w") as f:
                json.dump(self.cfg, f, indent=4)
                f.write("\n")
        except OSError as exc:
            print(f"[WARN] Could not save config: {exc}")

    def _set_dictation_language(self, code: str):
        """Set the dictation language and persist the change."""
        self.cfg.setdefault("dictation", {})["language"] = code
        self.dictation.language = code
        self._save_config()

    def _mux_send(self, key: str):
        """Send tmux/screen-style prefix key then a command key (default Ctrl+b)."""
        mux = self.cfg.get("mux", {}) or {}
        if not mux.get("enabled", True):
            log.debug("mux_send SKIPPED (disabled) key=%s", key)
            return
        pk = str(mux.get("prefix_key", "b"))
        delay = float(mux.get("after_prefix_delay_s", 0.05))
        log.debug("mux_send key=%s prefix_key=%s delay=%.3f", key, pk, delay)
        # Send Ctrl+key as raw control character via AppleScript —
        # pyautogui modifier keys are unreliable on macOS.
        # Ctrl+b = ASCII 2, Ctrl+a = ASCII 1, etc.
        ctrl_char = chr(ord(pk.lower()) - ord('a') + 1)
        script = (
            'tell application "System Events" to keystroke '
            f'(ASCII character {ord(ctrl_char)})'
        )
        subprocess.run(["osascript", "-e", script],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                       timeout=2)
        time.sleep(delay)
        pyautogui.press(key)

    def _fire_action(self, name: str):
        # Mux actions bypass the shortcut table
        if name == "mux_next_window":
            mux = self.cfg.get("mux", {}) or {}
            self._mux_send(str(mux.get("next_window_key", "n")))
            return
        if name == "mux_prev_window":
            mux = self.cfg.get("mux", {}) or {}
            self._mux_send(str(mux.get("prev_window_key", "p")))
            return
        spec = self.shortcuts.get(name)
        if spec is None:
            return
        if spec == ("click",):
            pyautogui.click()
            return
        if spec == ("rightClick",):
            pyautogui.rightClick()
            return
        if spec == ("doubleClick",):
            pyautogui.doubleClick()
            return
        log.debug("fire_action spec=%s", spec)
        self._send_hotkey(spec)

    # ---- reliable hotkey via Quartz CGEvents (works even when pygame has focus)

    _MODMAP = {
        "command": 0x000008,   # kCGEventFlagMaskCommand (bit 20 → 0x100000) — nope, use Quartz constants
        "shift":   0x020000,
        "control": 0x040000,
        "ctrl":    0x040000,
        "option":  0x080000,
        "alt":     0x080000,
    }

    # Map pyautogui key names → macOS virtual key codes
    _VKMAP = {
        "a": 0x00, "b": 0x0B, "c": 0x08, "d": 0x02, "e": 0x0E, "f": 0x03,
        "g": 0x05, "h": 0x04, "i": 0x22, "j": 0x26, "k": 0x28, "l": 0x25,
        "m": 0x2E, "n": 0x2D, "o": 0x1F, "p": 0x23, "q": 0x0C, "r": 0x0F,
        "s": 0x01, "t": 0x11, "u": 0x20, "v": 0x09, "w": 0x0D, "x": 0x07,
        "y": 0x10, "z": 0x06,
        "`": 0x32, "-": 0x1B, "=": 0x18, "[": 0x21, "]": 0x1E, "\\": 0x2A,
        ";": 0x29, "'": 0x27, ",": 0x2B, ".": 0x2F, "/": 0x2C,
        "space": 0x31, "return": 0x24, "tab": 0x30, "escape": 0x35,
        "delete": 0x33, "backspace": 0x33,
        "f1": 0x7A, "f2": 0x78, "f3": 0x63, "f4": 0x76, "f5": 0x60,
        "f6": 0x61, "f7": 0x62, "f8": 0x64, "f9": 0x65, "f10": 0x6D,
        "f11": 0x67, "f12": 0x6F,
        "up": 0x7E, "down": 0x7D, "left": 0x7B, "right": 0x7C,
    }

    def _send_hotkey(self, spec):
        """Send a hotkey combo via Quartz CGEvents — works regardless of window focus."""
        try:
            import Quartz
        except ImportError:
            log.warning("Quartz unavailable, falling back to pyautogui")
            pyautogui.hotkey(*spec)
            return

        mods = spec[:-1]
        key = spec[-1]
        vk = self._VKMAP.get(key)
        if vk is None:
            log.warning("No virtual keycode for %r, falling back to pyautogui", key)
            pyautogui.hotkey(*spec)
            return

        flags = 0
        for m in mods:
            f = self._MODMAP.get(m)
            if f:
                flags |= f
            else:
                log.warning("Unknown modifier %r, falling back to pyautogui", m)
                pyautogui.hotkey(*spec)
                return

        # CGEventFlagMaskCommand is actually 0x100000
        # Fix: use proper Quartz constants
        flag_remap = {
            0x000008: 0x100000,  # command
            0x020000: 0x020000,  # shift
            0x040000: 0x040000,  # control
            0x080000: 0x080000,  # option
        }
        real_flags = 0
        for m in mods:
            f = self._MODMAP.get(m)
            real_flags |= flag_remap.get(f, f)

        down = Quartz.CGEventCreateKeyboardEvent(None, vk, True)
        up = Quartz.CGEventCreateKeyboardEvent(None, vk, False)
        Quartz.CGEventSetFlags(down, real_flags)
        Quartz.CGEventSetFlags(up, real_flags)
        Quartz.CGEventPost(Quartz.kCGHIDEventTap, down)
        Quartz.CGEventPost(Quartz.kCGHIDEventTap, up)

    def _init_pygame(self):
        os.environ["SDL_VIDEO_ALLOW_SCREENSAVER"] = "1"
        # Critical: keep receiving joystick events even when window is not focused
        os.environ["SDL_JOYSTICK_ALLOW_BACKGROUND_EVENTS"] = "1"
        pygame.init()
        pygame.joystick.init()

        self.screen = pygame.display.set_mode((720, 540), pygame.RESIZABLE)
        pygame.display.set_caption("Vibe Control")
        self._set_app_icon()
        self.font = pygame.font.SysFont("helveticaneue", 15)
        self.font_lg = pygame.font.SysFont("helveticaneue", 19, bold=True)
        self.font_sm = pygame.font.SysFont("helveticaneue", 13)
        self.font_mono = pygame.font.SysFont("menlo", 12)

        if pygame.joystick.get_count() == 0:
            print("[ERROR] No controller detected. Plug in your controller and retry.")
            pygame.quit()
            sys.exit(1)

    def _set_app_icon(self):
        """Set the window icon from PNG (called during init)."""
        base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
        png_path = os.path.join(base, "vibecontrol_logo.png")
        if os.path.isfile(png_path):
            try:
                icon_surf = pygame.image.load(png_path)
                pygame.display.set_icon(icon_surf)
            except Exception:
                pass

    def _set_dock_icon(self):
        """Set macOS dock icon and process name via AppKit.

        Called after the first frame renders so SDL has finished its own
        icon setup and we can safely override the dock tile."""
        base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
        icns_path = os.path.join(base, "VibeControl.icns")
        png_path = os.path.join(base, "vibecontrol_logo.png")
        try:
            from AppKit import NSApplication, NSImage, NSProcessInfo
            app = NSApplication.sharedApplication()
            icon_file = icns_path if os.path.isfile(icns_path) else png_path
            if os.path.isfile(icon_file):
                img = NSImage.alloc().initByReferencingFile_(icon_file)
                if img:
                    img.setSize_((512, 512))
                    app.setApplicationIconImage_(img)
            NSProcessInfo.processInfo().setValue_forKey_("Vibe Control", "processName")
        except Exception:
            pass

    def _init_joystick(self):
        self.js = pygame.joystick.Joystick(0)
        self.js.init()
        self._js_instance_id = self.js.get_instance_id()
        self._init_time = time.monotonic()
        name = self.js.get_name()
        nb, na, nh = self.js.get_numbuttons(), self.js.get_numaxes(), self.js.get_numhats()
        print(f"[OK] {name}  (buttons={nb}  axes={na}  hats={nh})")
        log.info("Controller: %s  buttons=%d axes=%d hats=%d", name, nb, na, nh)
        log.info("btn_rev mapping: %s", self.btn_rev)
        if nh == 0:
            print("     D-pad mapped as buttons (no hats)")

        # Rumble queue: list of (fire_at_monotonic, low, high, duration_ms)
        # Processed on the main thread each frame — SDL is NOT thread-safe.
        self._rumble_queue = []
        self._rumble_use_native = False  # True if SDL rumble fails → use HID

        # Native HID rumble for DualSense — SDL rumble silently fails on
        # macOS (returns True but no vibration).  Use IOKit instead.
        self._native_rumble = DualSenseRumble()
        if DualSenseRumble.available():
            bt = detect_hid_bt()
            self._native_rumble.probe(bluetooth=bt)
            self._rumble_use_native = True
            transport = "Bluetooth" if bt else "USB"
            print(f"     {transport} HID — using native rumble")

        if self.vib_on_startup:
            self._queue_rumble_pattern([
                (0.4,  0.4, 0.4, 60),
                (0.52, 0.4, 0.4, 60),
                (0.64, 0.4, 0.4, 60),
                (0.76, 0.4, 0.4, 60),
            ])

    # ---------------------------------------------------------- vibration

    def _queue_rumble_pattern(self, pattern):
        """Queue rumble pulses: list of (delay_seconds, low, high, duration_ms).
        All pulses execute on the main thread via _process_rumble_queue()."""
        if not self.vib_enabled:
            return
        now = time.monotonic()
        for delay, low, high, dur in pattern:
            self._rumble_queue.append((now + delay, low, high, dur))

    def _tick_approval_prompt_vibration(self, now: float):
        """Alert burst on first detection + gentle alternating rumble while prompt is visible."""
        if (
            not self.vib_enabled
            or not self.vib_on_approval_prompt
            or self.discover
        ):
            self._approval_prompt_active = False
            return
        if now - self._approval_scan_t >= self.approval_scan_interval_s:
            self._approval_scan_t = now
            was_active = self._approval_prompt_active
            try:
                self._approval_prompt_active = approval_prompt_active()
            except Exception:
                self._approval_prompt_active = False
            # Strong alert burst on the transition from inactive → active
            if self._approval_prompt_active and not was_active:
                self._queue_rumble_pattern([
                    (0.0, 0.6, 0.6, 120),   # strong double-tap
                    (0.15, 0.0, 0.0, 60),   # brief pause
                    (0.0, 0.6, 0.6, 120),   # second tap
                ])
                self._approval_pulse_t = now  # reset pulse timer after burst
                return
        if not self._approval_prompt_active:
            return
        if now - self._approval_pulse_t < self.approval_pulse_interval_s:
            return
        self._approval_pulse_t = now
        self._approval_pulse_phase = not self._approval_pulse_phase
        if self._approval_pulse_phase:
            self._queue_rumble_pattern([(0.0, 0.12, 0.28, 42)])
        else:
            self._queue_rumble_pattern([(0.0, 0.28, 0.12, 42)])

    def _process_rumble_queue(self):
        if not self._rumble_queue:
            return
        now = time.monotonic()
        remaining = []
        for fire_at, low, high, dur in self._rumble_queue:
            if now >= fire_at:
                if self._rumble_use_native:
                    self._native_rumble.rumble(low, high, dur)
                    # IOKit doesn't auto-stop — schedule a stop after duration
                    if low > 0 or high > 0:
                        remaining.append((now + dur / 1000.0, 0, 0, 0))
                else:
                    try:
                        self.js.rumble(low, high, dur)
                    except Exception:
                        pass
            else:
                remaining.append((fire_at, low, high, dur))
        self._rumble_queue = remaining

    def _vibrate_dictation_start(self):
        self._queue_rumble_pattern([(0.0, 0.3, 0.6, 120)])

    def _vibrate_dictation_stop(self):
        self._queue_rumble_pattern([
            (0.0,  0.2, 0.4, 80),
            (0.12, 0.2, 0.4, 80),
        ])

    def _vibrate_mode_change(self):
        self._queue_rumble_pattern([(0.0, 0.15, 0.3, 80)])

    # ---------------------------------------------------------- helpers

    def _dz(self, v, dz=None):
        dz = dz or self.deadzone
        if abs(v) < dz:
            return 0.0
        sign = 1 if v > 0 else -1
        return sign * (abs(v) - dz) / (1.0 - dz)

    def _curve(self, v):
        return math.copysign(abs(v) ** self.accel, v)

    def _throttled(self, key, ms):
        now = time.monotonic() * 1000
        if now - self._ts.get(key, 0) < ms:
            return True
        self._ts[key] = now
        return False

    def _l2_chord_gate(self):
        """True when L2 is pulled enough to pair with X/O for prompt shortcuts."""
        try:
            ax_idx = self.ax["l2_trigger"]
            if self.js.get_numaxes() <= ax_idx:
                return False
            v = self.js.get_axis(ax_idx)
            return v > 0.2
        except Exception:
            return False

    # ---------------------------------------------------------- mouse

    def _handle_mouse(self):
        lx = self._dz(self.js.get_axis(self.ax["left_x"]))
        ly = self._dz(self.js.get_axis(self.ax["left_y"]))
        if lx == 0 and ly == 0:
            return

        if self.l1_held:
            self._stick_arrows(lx, ly)
            return

        speed = self.speeds[self.speed_idx] * self.sensitivity

        # L2 held → precision slow-down
        if self.js.get_numaxes() > self.ax["l2_trigger"]:
            l2 = self.js.get_axis(self.ax["l2_trigger"])
            if l2 > -0.9:
                precision = 1.0 - ((l2 + 1) / 2) * 0.75
                speed *= max(precision, 0.15)

        dx = self._curve(lx) * speed
        dy = self._curve(ly) * speed
        pyautogui.moveRel(dx, dy)

    def _stick_arrows(self, x, y):
        """Code-mode: left stick sends arrow keys (throttled)."""
        if self._throttled("arrows", 120):
            return
        if abs(x) > 0.5:
            pyautogui.press("right" if x > 0 else "left")
        if abs(y) > 0.5:
            pyautogui.press("down" if y > 0 else "up")

    # ---------------------------------------------------------- scroll

    def _handle_scroll(self):
        rx = self._dz(self.js.get_axis(self.ax["right_x"]), self.scroll_dz)
        ry = self._dz(self.js.get_axis(self.ax["right_y"]), self.scroll_dz)
        if rx == 0 and ry == 0:
            return
        if self._throttled("scroll", self.scroll_throttle):
            return

        if ry != 0:
            pyautogui.scroll(int(-ry * self.scroll_v))
        if rx != 0:
            pyautogui.hscroll(int(rx * self.scroll_h))

    # ---------------------------------------------------------- buttons

    def _btn_down(self, idx):
        name = self.btn_rev.get(idx, f"?{idx}")
        log.debug("btn_down idx=%d name=%s guide_overlay=%s", idx, name, self.guide_overlay)
        if self.discover:
            print(f"  BTN DOWN  idx={idx}  name={name}")
            return

        if self.guide_overlay:
            if name in ("circle", "ps"):
                self._close_guide_overlay()
                return
            if (name == "share" and self._joy_button("options")) or (
                name == "options" and self._joy_button("share")
            ):
                if not self._throttled("guide_combo", 280):
                    self._close_guide_overlay()
                return
            return

        if (name == "share" and self._joy_button("options")) or (
            name == "options" and self._joy_button("share")
        ):
            if not self._throttled("guide_combo", 280):
                self._toggle_guide_overlay()
            return

        # D-pad buttons (when controller reports hats=0)
        if name.startswith("dpad_"):
            direction = name.removeprefix("dpad_")
            self._dpad_press(direction)
            return

        # L2 + Cross / Circle — Run (Enter) / Esc for Cursor prompts (works in any mode, even if paused)
        if name in ("cross", "circle") and self._l2_chord_gate():
            if name == "cross":
                if not self._throttled("l2_prompt_enter", 400):
                    self._fire_action("enter")
                return
            if not self._throttled("l2_prompt_esc", 400):
                self._fire_action("escape")
            return

        if name == "l1":
            self.l1_held = True
            self.mode = "CODE"
            if self.vib_on_mode_change:
                self._vibrate_mode_change()
            return
        if name == "r1":
            if self.vib_on_dictation:
                self._vibrate_dictation_start()
            self._dictation_send_after = False
            self.dictation.start_recording()
            return
        if name == "touchpad" and not self.l1_held:
            # "Speak to Cursor AI" — open chat, dictate, paste, send
            if self.vib_on_dictation:
                self._vibrate_dictation_start()
            self._fire_action("ai_chat")
            time.sleep(0.15)
            self._dictation_send_after = True
            self.dictation.start_recording()
            return
        if name == "ps":
            self.active = not self.active
            tag = "ACTIVE" if self.active else "PAUSED"
            print(f"\n  [{tag}]")
            return
        if name == "r3" and not self.l1_held:
            self.speed_idx = (self.speed_idx + 1) % len(self.speeds)
            print(f"\n  Speed → {SPEED_LABELS[self.speed_idx]}")
            return
        if not self.active:
            return

        action_map = self.code_actions if self.l1_held else self.normal_actions
        action = action_map.get(name)
        if action:
            self._fire_action(action)

    def _btn_up(self, idx):
        name = self.btn_rev.get(idx)
        if name == "l1":
            self.l1_held = False
            self.mode = "NORMAL"
        elif name in ("r1", "touchpad"):
            self.dictation.stop_recording()
            if self.vib_on_dictation:
                self._vibrate_dictation_stop()

    # ---------------------------------------------------------- dpad / hat

    def _hat_motion(self, hx, hy):
        log.debug("hat_motion hx=%d hy=%d", hx, hy)
        if self.discover:
            print(f"  HAT  x={hx}  y={hy}")
            return

        new = {"up": hy == 1, "down": hy == -1, "left": hx == -1, "right": hx == 1}
        for d in ("up", "down", "left", "right"):
            if new[d] and not self._dpad[d]:
                self._dpad_press(d)
        self._dpad = new

    def _dpad_press(self, direction):
        # Normal mode only: L2 + D-pad hops Terminal windows (Cmd+`) / tmux panes (prefix+n/p).
        # Skipped in code mode so L2 + D-pad still maps to IDE shortcuts.
        l2_gate = self._l2_chord_gate()
        log.debug("dpad_press dir=%s l1_held=%s l2_gate=%s active=%s",
                  direction, self.l1_held, l2_gate, self.active)
        if (
            not self.l1_held
            and l2_gate
            and direction in ("left", "right", "up", "down")
        ):
            if direction == "left" and not self._throttled("l2_dpad_prev_pane", 350):
                self._fire_action("prev_pane")
            elif direction == "right" and not self._throttled("l2_dpad_next_pane", 350):
                self._fire_action("next_pane")
            elif direction == "up" and not self._throttled("l2_dpad_prev_win", 350):
                self._fire_action("prev_app_window")
            elif direction == "down" and not self._throttled("l2_dpad_next_win", 350):
                self._fire_action("next_app_window")
            return
        if not self.active:
            return
        key = f"dpad_{direction}"
        action_map = self.code_actions if self.l1_held else self.normal_actions
        action = action_map.get(key)
        if action:
            self._fire_action(action)

    # ---------------------------------------------------------- R2 trigger

    def _check_r2(self):
        """R2 full pull → Enter key (throttled)."""
        if self.js.get_numaxes() <= self.ax["r2_trigger"]:
            return
        val = self.js.get_axis(self.ax["r2_trigger"])
        if val > 0.8 and not self._throttled("r2", 300):
            action_map = self.code_actions if self.l1_held else self.normal_actions
            action = action_map.get("r2_trigger", "enter")
            self._fire_action(action)

    # ---------------------------------------------------------- dictation

    def _on_text(self, text):
        """Paste transcribed text into the focused window."""
        send = self._dictation_send_after
        self._dictation_send_after = False
        tag = "AI" if send else "Dictation"
        print(f'\n  {tag}: "{text}"')
        proc = subprocess.Popen(["pbcopy"], stdin=subprocess.PIPE)
        proc.communicate(text.encode("utf-8"))
        time.sleep(0.05)
        pyautogui.hotkey("command", "v")
        if send:
            time.sleep(0.1)
            pyautogui.press("return")

    def _on_dict_status(self, status):
        self.dictation_status = status.upper()

    # ---------------------------------------------------------- display

    def _read_axis_safe(self, name):
        try:
            return self.js.get_axis(self.ax[name])
        except Exception:
            return 0.0

    def _joy_button(self, logical_name: str) -> bool:
        idx = self.btn.get(logical_name)
        if idx is None or idx >= self.js.get_numbuttons():
            return False
        return bool(self.js.get_button(idx))

    def _toggle_guide_overlay(self):
        self.guide_overlay = not self.guide_overlay
        self.guide_scroll = 0
        if self.guide_overlay:
            self._clamp_guide_scroll()
            print("\n  [INFO] Binding guide - O / PS / Options+Share / Esc to close")

    def _close_guide_overlay(self):
        self.guide_overlay = False
        self.guide_scroll = 0

    def _guide_content_height(self) -> int:
        return len(_GUIDE_LINES) * _GUIDE_LINE_H + 24

    def _clamp_guide_scroll(self):
        _, h = self.screen.get_size()
        view_h = max(120, h - 48 - 88)
        ch = self._guide_content_height()
        mx = max(0, ch - view_h)
        self.guide_scroll = max(0, min(self.guide_scroll, mx))

    def _handle_guide_overlay_scroll(self):
        ry = self._dz(self.js.get_axis(self.ax["right_y"]), 0.22)
        if abs(ry) < 0.12:
            return
        if self._throttled("guide_rs", 32):
            return
        self.guide_scroll += int(-ry * 16)
        self._clamp_guide_scroll()

    def _draw_guide_overlay(self):
        w, h = self.screen.get_size()
        dim = pygame.Surface((w, h), pygame.SRCALPHA)
        dim.fill((0, 0, 0, 210))
        self.screen.blit(dim, (0, 0))

        panel = pygame.Rect(20, 20, w - 40, h - 40)
        draw_rounded_rect_alpha(self.screen, (18, 18, 22), panel, 14, 250)
        pygame.draw.rect(self.screen, COL_ACCENT, panel, width=2, border_radius=14)

        title = self.font_lg.render("Binding guide", True, COL_ACCENT)
        self.screen.blit(title, (panel.x + 20, panel.y + 16))
        sub = self.font_sm.render("DualSense > Cursor & macOS", True, COL_TEXT_MUTED)
        self.screen.blit(sub, (panel.x + 20, panel.y + 44))

        body_top = panel.y + 78
        body_h = panel.h - 78 - 56
        body_rect = pygame.Rect(panel.x + 16, body_top, panel.w - 32, body_h)
        pygame.draw.rect(self.screen, (12, 12, 14), body_rect, border_radius=10)
        pygame.draw.rect(self.screen, COL_BORDER, body_rect, width=1, border_radius=10)

        prev_clip = self.screen.get_clip()
        self.screen.set_clip(body_rect)
        y = body_rect.y + 10 - self.guide_scroll
        for line in _GUIDE_LINES:
            if y + _GUIDE_LINE_H < body_rect.top or y > body_rect.bottom:
                y += _GUIDE_LINE_H
                continue
            if not line.strip():
                y += _GUIDE_LINE_H
                continue
            is_head = line.startswith(">> ")
            col = COL_ACCENT if is_head else COL_TEXT
            f = self.font_sm
            txt = line[3:].strip() if is_head else line
            surf = f.render(txt, True, col)
            self.screen.blit(surf, (body_rect.x + 12, y))
            y += _GUIDE_LINE_H
        self.screen.set_clip(prev_clip)

        close = pygame.Rect(panel.centerx - 70, panel.bottom - 48, 140, 36)
        self._guide_close_r = close
        hov = close.collidepoint(pygame.mouse.get_pos())
        draw_rounded_rect(self.screen, COL_SURFACE_HOVER if hov else COL_SURFACE, close, 8)
        pygame.draw.rect(self.screen, COL_ACCENT, close, width=1, border_radius=8)
        ct = self.font_sm.render("Close", True, COL_TEXT)
        self.screen.blit(ct, (close.centerx - ct.get_width() // 2, close.centery - ct.get_height() // 2))

    def _draw(self):
        if self.discover:
            w, h = self.screen.get_size()
            draw_vertical_gradient(self.screen, w, h)
            t = self.font_lg.render("Discover mode", True, COL_TEXT)
            self.screen.blit(t, (20, 20))
            self.screen.blit(
                self.font_sm.render("Watch terminal for button / axis output.", True, COL_TEXT_MUTED),
                (20, 48),
            )
            pygame.display.flip()
            return

        if self.ui_panel == "bindings":
            self._draw_bindings()
        elif self.ui_panel == "dictation":
            self._draw_dictation()
        else:
            self._draw_dashboard()
        if self.guide_overlay:
            self._draw_guide_overlay()
        pygame.display.flip()

    def _layout_tabs(self, w, margin=20):
        y = 16
        pill_h = 34
        self._tab_dash_r = pygame.Rect(margin, y, 118, pill_h)
        self._tab_bind_r = pygame.Rect(margin + 126, y, 118, pill_h)
        self._tab_dict_r = pygame.Rect(margin + 252, y, 118, pill_h)

    def _bindings_list_geometry(self):
        w, h = self.screen.get_size()
        list_top = 58 + 52 + 10
        list_h = max(100, h - list_top - 56)
        inner_w = w - 32
        return list_top, list_h, inner_w

    def _clamp_bind_scroll(self):
        _, list_h, _ = self._bindings_list_geometry()
        n = len(self._bind_action_ids)
        max_s = max(0, n * BIND_ROW_H - list_h + 24)
        self._bind_scroll = max(0, min(self._bind_scroll, max_s))

    def _apply_shortcut_override(self, action_id: str, spec: tuple):
        self.cfg.setdefault("shortcut_overrides", {})
        self.cfg["shortcut_overrides"][action_id] = list(spec)
        self._rebuild_shortcuts()
        self._save_config()
        self._bind_recording_action = None

    def _draw_dashboard(self):
        w, h = self.screen.get_size()
        mx, my = pygame.mouse.get_pos()
        draw_vertical_gradient(self.screen, w, h, COL_BG_TOP, COL_BG_BOT)

        # --- tabs ---
        self._layout_tabs(w)
        draw_pill(self.screen, self.font_sm, "Dashboard", self._tab_dash_r, active=True)
        hov_b = self._tab_bind_r.collidepoint(mx, my)
        draw_pill(self.screen, self.font_sm, "Bindings", self._tab_bind_r, hover=hov_b)
        hov_dc = self._tab_dict_r.collidepoint(mx, my)
        draw_pill(self.screen, self.font_sm, "Dictation", self._tab_dict_r, hover=hov_dc)

        # --- main card ---
        panel = pygame.Rect(16, 62, w - 32, h - 78)
        draw_card(self.screen, panel, radius=16, alpha=240, glow=self.active)
        px, py = panel.x + 24, panel.y

        # row 1: title + subtitle + paused badge
        title = self.font_lg.render("Vibe Control", True, COL_ACCENT)
        self.screen.blit(title, (px, py + 14))
        sub = self.font_sm.render("DualSense controller for macOS", True, COL_TEXT_MUTED)
        self.screen.blit(sub, (px, py + 38))

        if not self.active:
            badge = pygame.Rect(panel.right - 100, py + 16, 74, 26)
            draw_rounded_rect_alpha(self.screen, COL_DANGER, badge, badge.h // 2, 35)
            pygame.draw.rect(self.screen, COL_DANGER, badge, width=1, border_radius=badge.h // 2)
            p = self.font_sm.render("PAUSED", True, COL_DANGER)
            self.screen.blit(p, (badge.centerx - p.get_width() // 2,
                                 badge.centery - p.get_height() // 2))

        # --- divider ---
        div_y = py + 58
        draw_soft_divider(self.screen, px, panel.right - 24, div_y)

        # row 2: mode + speed chips (clickable, with labels)
        label_y = div_y + 12
        chip_y = label_y + 18

        # Input Mode
        self.screen.blit(self.font_sm.render("Input Mode", True, COL_TEXT_MUTED), (px, label_y))
        mode_active = self.mode == "NORMAL"
        self._mode_chip_r = pygame.Rect(px, chip_y, 100, 28)
        hov_mode = self._mode_chip_r.collidepoint(mx, my)
        draw_chip(self.screen, self.font_sm, self.mode, self._mode_chip_r,
                  color=COL_ACCENT if mode_active else (200, 60, 80),
                  border_color=COL_ACCENT if mode_active else (200, 60, 80),
                  bg_color=(40, 12, 18),
                  hover=hov_mode)

        # Mouse Speed
        spd_x = px + 130
        self.screen.blit(self.font_sm.render("Mouse Speed", True, COL_TEXT_MUTED), (spd_x, label_y))
        self._speed_chip_r = pygame.Rect(spd_x, chip_y, 100, 28)
        hov_spd = self._speed_chip_r.collidepoint(mx, my)
        draw_chip(self.screen, self.font_sm, SPEED_LABELS[self.speed_idx],
                  self._speed_chip_r, hover=hov_spd)

        # --- sticks + triggers section ---
        sec_y = chip_y + 44
        stick_r = 32
        gap = 40

        # left stick
        ls_cx = px + stick_r + 8
        ls_cy = sec_y + stick_r + 14
        lbl_s = self.font_sm.render("Mouse", True, COL_TEXT_DIM)
        self.screen.blit(lbl_s, (ls_cx - lbl_s.get_width() // 2, sec_y))
        self._draw_stick(ls_cx, ls_cy, "left_x", "left_y", stick_r)

        # right stick
        rs_cx = ls_cx + stick_r * 2 + gap + stick_r
        rs_cy = ls_cy
        lbl_r = self.font_sm.render("Scroll", True, COL_TEXT_DIM)
        self.screen.blit(lbl_r, (rs_cx - lbl_r.get_width() // 2, sec_y))
        self._draw_stick(rs_cx, rs_cy, "right_x", "right_y", stick_r)

        # triggers — right-aligned
        trig_x = panel.right - 90
        trig_y = sec_y
        self._draw_trigger(trig_x, trig_y + 14, "L2", "l2_trigger")
        self._draw_trigger(trig_x + 40, trig_y + 14, "R2", "r2_trigger")

        # --- mic bar ---
        mic_y = max(ls_cy + stick_r + 20, sec_y + 94)
        mic_box = pygame.Rect(px, mic_y, panel.w - 48, 40)
        draw_frosted_panel(self.screen, mic_box, radius=12)
        recording = "RECORD" in self.dictation_status

        # mic indicator dot with glow
        dot_cx, dot_cy = mic_box.x + 18, mic_box.centery
        if recording:
            draw_glow_circle(self.screen, (dot_cx, dot_cy), 5, COL_ACCENT, intensity=80)
        else:
            pygame.draw.circle(self.screen, COL_TEXT_DIM, (dot_cx, dot_cy), 4)
            pygame.draw.circle(self.screen, COL_BORDER, (dot_cx, dot_cy), 4, 1)

        if recording:
            lbl = "RECORDING ..."
            lbl_c = COL_ACCENT
        elif not self.dictation.mic_available and self._native_rumble.is_bluetooth:
            lbl = "Mic - NO MIC (BT, use USB)"
            lbl_c = COL_TEXT_MUTED
        else:
            lbl = f"Mic - {self.dictation_status}"
            lbl_c = COL_TEXT
        self.screen.blit(self.font.render(lbl, True, lbl_c), (mic_box.x + 34, mic_box.y + 12))

        # --- language selector (right side of mic bar) ---
        cur_lang = self.cfg.get("dictation", {}).get("language", "en-US")
        lang_label = cur_lang
        for name, code in DICTATION_LANGUAGES:
            if code == cur_lang:
                lang_label = name
                break
        lang_text = lang_label
        tw = self.font_sm.size(lang_text)[0]
        arrow_space = 16  # space for dropdown arrow triangle
        chip_w = tw + 24 + arrow_space
        self._lang_chip_r = pygame.Rect(mic_box.right - chip_w - 6, mic_box.y + 6, chip_w, 28)
        hov_lang = self._lang_chip_r.collidepoint(mx, my) and not self._lang_dropdown_open
        chip_open = self._lang_dropdown_open
        # chip background
        if chip_open:
            draw_rounded_rect_alpha(self.screen, COL_ACCENT, self._lang_chip_r,
                                    radius=self._lang_chip_r.h // 2, alpha=220)
        elif hov_lang:
            draw_rounded_rect_alpha(self.screen, COL_SURFACE_HOVER, self._lang_chip_r,
                                    radius=self._lang_chip_r.h // 2, alpha=200)
        else:
            draw_rounded_rect_alpha(self.screen, (26, 26, 30), self._lang_chip_r,
                                    radius=self._lang_chip_r.h // 2, alpha=180)
        border_c = COL_ACCENT if (chip_open or hov_lang) else COL_BORDER_SUBTLE
        pygame.draw.rect(self.screen, border_c, self._lang_chip_r, width=1,
                         border_radius=self._lang_chip_r.h // 2)
        chip_tc = (255, 255, 255) if chip_open else (COL_TEXT if hov_lang else COL_TEXT_MUTED)
        chip_surf = self.font_sm.render(lang_text, True, chip_tc)
        self.screen.blit(chip_surf, (self._lang_chip_r.x + 12,
                                     self._lang_chip_r.centery - chip_surf.get_height() // 2))
        # dropdown arrow (small triangle)
        arrow_x = self._lang_chip_r.right - 16
        arrow_y = self._lang_chip_r.centery
        pygame.draw.polygon(self.screen, chip_tc,
                            [(arrow_x - 3, arrow_y - 2),
                             (arrow_x + 3, arrow_y - 2),
                             (arrow_x, arrow_y + 2)])

        # --- language dropdown ---
        if self._lang_dropdown_open:
            self._draw_lang_dropdown(mx, my, cur_lang)

        # --- hint footer (auto-truncate to fit panel) ---
        foot_y = panel.bottom - 32
        hints = "Opt+Share=guide | L2+X/O=Enter/Esc | R1=mic | L1=code | PS=pause"
        max_hint_w = panel.w - 48
        hints_surf = self.font_sm.render(hints, True, COL_TEXT_DIM)
        if hints_surf.get_width() > max_hint_w:
            hints = self._truncate_to_width(self.font_sm, hints, max_hint_w)
            hints_surf = self.font_sm.render(hints, True, COL_TEXT_DIM)
        self.screen.blit(hints_surf, (px, foot_y))

    def _draw_lang_dropdown(self, mx, my, cur_lang):
        """Draw the language dropdown menu with scroll support."""
        drop_row_h = 32
        drop_w = 230
        pad = 6
        drop_x = self._lang_chip_r.right - drop_w
        drop_y = self._lang_chip_r.bottom + 6
        n = len(DICTATION_LANGUAGES)
        full_h = n * drop_row_h + pad * 2

        # Clamp height to fit in window
        _, screen_h = self.screen.get_size()
        max_h = screen_h - drop_y - 12
        drop_h = min(full_h, max_h)
        scrollable = full_h > drop_h

        # Clamp scroll
        max_scroll = max(0, full_h - drop_h)
        self._lang_dropdown_scroll = max(0, min(self._lang_dropdown_scroll, max_scroll))

        drop_panel = pygame.Rect(drop_x, drop_y, drop_w, drop_h)
        self._lang_dropdown_panel = drop_panel

        # shadow + background
        draw_shadow(self.screen, drop_panel, radius=14, offset=6, alpha=100)
        draw_shadow(self.screen, drop_panel, radius=14, offset=3, alpha=50)
        draw_frosted_panel(self.screen, drop_panel, radius=14, alpha=245)

        # subtle accent line at top
        accent_line = pygame.Surface((drop_w - 28, 1), pygame.SRCALPHA)
        lw = accent_line.get_width()
        for bx in range(lw):
            fade = min(bx, lw - bx) / max(lw * 0.25, 1)
            fade = min(fade, 1.0)
            accent_line.set_at((bx, 0), (*COL_ACCENT[:3], int(fade * 50)))
        self.screen.blit(accent_line, (drop_x + 14, drop_y + 2))

        # Clip to panel and draw rows with scroll offset
        prev_clip = self.screen.get_clip()
        self.screen.set_clip(drop_panel)

        self._lang_dropdown_rects = []
        for i, (name, code) in enumerate(DICTATION_LANGUAGES):
            ry = drop_y + pad + i * drop_row_h - self._lang_dropdown_scroll
            row_r = pygame.Rect(drop_x + pad, ry, drop_w - pad * 2, drop_row_h)

            # Skip rows fully outside visible area (but still register for clicks)
            visible = ry + drop_row_h > drop_panel.top and ry < drop_panel.bottom
            self._lang_dropdown_rects.append((row_r, code))
            if not visible:
                continue

            is_cur = code == cur_lang
            hov = row_r.collidepoint(mx, my)

            if is_cur:
                draw_rounded_rect_alpha(self.screen, COL_ACCENT, row_r, radius=8, alpha=190)
            elif hov:
                draw_rounded_rect_alpha(self.screen, COL_SURFACE_HOVER, row_r, radius=8, alpha=180)

            cy = row_r.centery
            if is_cur:
                check = self.font_sm.render("*", True, (255, 255, 255))
                self.screen.blit(check, (row_r.x + 10, cy - check.get_height() // 2))

            name_x = row_r.x + 30
            text_c = (255, 255, 255) if is_cur else (COL_TEXT if hov else COL_TEXT_MUTED)
            name_surf = self.font_sm.render(name, True, text_c)
            self.screen.blit(name_surf, (name_x, cy - name_surf.get_height() // 2))

            code_c = (255, 255, 255, 140) if is_cur else COL_TEXT_DIM
            code_surf = self.font_sm.render(code, True, code_c[:3] if len(code_c) > 3 else code_c)
            self.screen.blit(code_surf, (row_r.right - code_surf.get_width() - 10,
                                         cy - code_surf.get_height() // 2))

        self.screen.set_clip(prev_clip)

        # Scroll indicators
        if scrollable:
            if self._lang_dropdown_scroll > 0:
                # fade at top
                for fy in range(8):
                    a = int(200 * (1.0 - fy / 8.0))
                    pygame.draw.line(self.screen, (20, 20, 24, a) if a > 0 else (20, 20, 24),
                                     (drop_x + 4, drop_y + fy), (drop_x + drop_w - 4, drop_y + fy))
            if self._lang_dropdown_scroll < max_scroll:
                # fade at bottom
                for fy in range(8):
                    a = int(200 * (fy / 8.0))
                    by = drop_panel.bottom - 8 + fy
                    pygame.draw.line(self.screen, (20, 20, 24),
                                     (drop_x + 4, by), (drop_x + drop_w - 4, by))

    def _draw_bindings(self):
        w, h = self.screen.get_size()
        mx, my = pygame.mouse.get_pos()
        draw_vertical_gradient(self.screen, w, h, COL_BG_TOP, COL_BG_BOT)

        self._layout_tabs(w)
        hov_d = self._tab_dash_r.collidepoint(mx, my)
        draw_pill(self.screen, self.font_sm, "Dashboard", self._tab_dash_r, active=False, hover=hov_d)
        draw_pill(self.screen, self.font_sm, "Bindings", self._tab_bind_r, active=True, hover=False)
        hov_dc = self._tab_dict_r.collidepoint(mx, my)
        draw_pill(self.screen, self.font_sm, "Dictation", self._tab_dict_r, hover=hov_dc)

        head = pygame.Rect(16, 58, w - 32, 52)
        draw_search_bar(
            self.screen,
            self.font,
            head,
            "Controller > Keyboard",
            "DualSense combos on each row - click row, Enter to change keystroke",
        )

        list_top, list_h, _ = self._bindings_list_geometry()
        panel = pygame.Rect(16, list_top, w - 32, list_h)
        draw_card(self.screen, panel, radius=14, alpha=235)

        inner_w = panel.w - 24
        self._bind_rows = []
        y0 = panel.y + 8 - self._bind_scroll
        visible_top = panel.y + 8
        visible_bot = panel.bottom - 8

        for idx, aid in enumerate(self._bind_action_ids):
            ry = y0 + idx * BIND_ROW_H
            if ry + BIND_ROW_H < visible_top or ry > visible_bot:
                self._bind_rows.append((pygame.Rect(0, 0, 0, 0), aid))
                continue
            row_rect = pygame.Rect(panel.x + 12, ry, inner_w, BIND_ROW_H - 4)
            self._bind_rows.append((row_rect, aid))
            sel = idx == self._bind_selected_idx
            hov = row_rect.collidepoint(mx, my) and not self._bind_recording_action
            if sel:
                draw_rounded_rect_alpha(self.screen, COL_ACCENT, row_rect, radius=10, alpha=190)
            else:
                bg = COL_SURFACE_HOVER if hov else (30, 30, 34)
                draw_rounded_rect(self.screen, bg, row_rect, radius=10)
                pygame.draw.rect(self.screen, COL_BORDER_SUBTLE if not hov else COL_BORDER,
                                 row_rect, width=1, border_radius=10)

            spec = self.shortcuts.get(aid, ())
            if spec == ("click",):
                chord_txt = "Left click"
            elif spec == ("rightClick",):
                chord_txt = "Right click"
            elif spec == ("doubleClick",):
                chord_txt = "Double click"
            else:
                chord_txt = format_chord(spec)
            chord_surf = self.font_mono.render(chord_txt, True, COL_TEXT_MUTED)
            chord_w = chord_surf.get_width()
            max_combo_w = max(60, row_rect.w - 24 - chord_w - 16)

            combo_raw = self._controller_combo_summary(aid)
            combo_txt = self._truncate_to_width(self.font_sm, combo_raw, max_combo_w)
            self.screen.blit(self.font_sm.render(combo_txt, True, COL_ACCENT), (row_rect.x + 12, row_rect.y + 6))

            label = ACTION_LABELS.get(aid, aid.replace("_", " ").title())
            self.screen.blit(self.font_sm.render(label, True, COL_TEXT), (row_rect.x + 12, row_rect.y + 28))

            self.screen.blit(
                chord_surf,
                (row_rect.right - chord_w - 12, row_rect.centery - chord_surf.get_height() // 2),
            )

        foot = pygame.Rect(16, h - 42, w - 32, 30)
        if self._bind_recording_action:
            aid = self._bind_recording_action
            lab = ACTION_LABELS.get(aid, aid)
            msg = f"Press a key combo...  Enter=save | Esc=cancel  ({lab})"
            if aid in MOUSE_ACTIONS:
                msg = f"Click Left / Right / Double below | Esc=cancel  ({lab})"
            self.screen.blit(self.font_sm.render(msg, True, COL_ACCENT), (foot.x + 8, foot.y + 8))
            if aid in MOUSE_ACTIONS:
                self._draw_mouse_chips(foot.x + 8, foot.y - 36)
        else:
            self.screen.blit(
                self.font_sm.render(
                    "Select row | Enter = set keystroke | Scroll = list",
                    True,
                    COL_TEXT_MUTED,
                ),
                (foot.x + 8, foot.y + 8),
            )

        rec = self._bind_recording_action
        if rec and rec not in MOUSE_ACTIONS:
            overlay = pygame.Rect(w // 2 - 140, 110, 280, 36)
            draw_shadow(self.screen, overlay, radius=12, offset=4, alpha=60)
            draw_frosted_panel(self.screen, overlay, radius=12, alpha=240)
            # pulsing accent border
            pygame.draw.rect(self.screen, COL_ACCENT, overlay, width=1, border_radius=12)
            self.screen.blit(self.font_sm.render("Listening for keys...", True, COL_TEXT),
                             (overlay.x + 16, overlay.y + 10))

    def _draw_mouse_chips(self, x, y):
        labels = [("Left", ("click",)), ("Right", ("rightClick",)), ("Double", ("doubleClick",))]
        self._mouse_chip_rects = []
        mx_pos, my_pos = pygame.mouse.get_pos()
        cx = x
        for lab, spec in labels:
            r = pygame.Rect(cx, y, 76, 28)
            self._mouse_chip_rects.append((r, spec))
            hov = r.collidepoint(mx_pos, my_pos)
            draw_chip(self.screen, self.font_sm, lab, r, hover=hov)
            cx += 84

    # ------------------------------------------------- dictation corrections tab

    def _get_corrections_list(self):
        """Return sorted list of (pattern, replacement) from config."""
        corr = self.cfg.get("dictation", {}).get("corrections", {})
        return sorted(corr.items(), key=lambda x: x[0].lower())

    def _dict_list_geometry(self):
        w, h = self.screen.get_size()
        list_top = 58 + 52 + 10
        list_h = max(100, h - list_top - 56)
        inner_w = w - 32
        return list_top, list_h, inner_w

    def _clamp_dict_scroll(self):
        _, list_h, _ = self._dict_list_geometry()
        items = self._get_corrections_list()
        n = len(items) + (1 if not self._dict_adding else 2)  # +1 for add button, +2 if adding
        max_s = max(0, n * BIND_ROW_H - list_h + 24)
        self._dict_scroll = max(0, min(self._dict_scroll, max_s))

    def _save_correction(self, pattern, replacement):
        """Add or update a correction in config and reload into DictationHandler."""
        if not pattern.strip():
            return
        self.cfg.setdefault("dictation", {}).setdefault("corrections", {})
        self.cfg["dictation"]["corrections"][pattern] = replacement
        self.dictation._corrections = self.dictation._compile_corrections(
            self.cfg["dictation"]["corrections"]
        )
        self._save_config()

    def _delete_correction(self, pattern):
        """Remove a correction from config and reload."""
        corr = self.cfg.get("dictation", {}).get("corrections", {})
        corr.pop(pattern, None)
        self.dictation._corrections = self.dictation._compile_corrections(corr)
        self._save_config()

    def _draw_dictation(self):
        w, h = self.screen.get_size()
        mx, my = pygame.mouse.get_pos()
        draw_vertical_gradient(self.screen, w, h, COL_BG_TOP, COL_BG_BOT)

        # --- tabs ---
        self._layout_tabs(w)
        hov_d = self._tab_dash_r.collidepoint(mx, my)
        draw_pill(self.screen, self.font_sm, "Dashboard", self._tab_dash_r, hover=hov_d)
        hov_b = self._tab_bind_r.collidepoint(mx, my)
        draw_pill(self.screen, self.font_sm, "Bindings", self._tab_bind_r, hover=hov_b)
        draw_pill(self.screen, self.font_sm, "Dictation", self._tab_dict_r, active=True)

        # --- header ---
        head = pygame.Rect(16, 58, w - 32, 52)
        draw_search_bar(
            self.screen, self.font, head,
            "Dictation corrections",
            "Speech-to-text replacements - fix misheard acronyms",
        )

        # --- list panel ---
        list_top, list_h, _ = self._dict_list_geometry()
        panel = pygame.Rect(16, list_top, w - 32, list_h)
        draw_card(self.screen, panel, radius=14, alpha=235)

        inner_w = panel.w - 24
        items = self._get_corrections_list()
        self._dict_rows = []
        y0 = panel.y + 8 - self._dict_scroll
        visible_top = panel.y + 8
        visible_bot = panel.bottom - 8

        for idx, (pattern, replacement) in enumerate(items):
            ry = y0 + idx * BIND_ROW_H
            if ry + BIND_ROW_H < visible_top or ry > visible_bot:
                self._dict_rows.append((pygame.Rect(0, 0, 0, 0), pattern))
                continue
            row_rect = pygame.Rect(panel.x + 12, ry, inner_w, BIND_ROW_H - 4)
            self._dict_rows.append((row_rect, pattern))
            sel = idx == self._dict_selected_idx
            hov = row_rect.collidepoint(mx, my) and not self._dict_editing and not self._dict_adding
            if sel:
                draw_rounded_rect_alpha(self.screen, COL_ACCENT, row_rect, radius=10, alpha=190)
            else:
                bg = COL_SURFACE_HOVER if hov else (30, 30, 34)
                draw_rounded_rect(self.screen, bg, row_rect, radius=10)
                pygame.draw.rect(self.screen, COL_BORDER_SUBTLE if not hov else COL_BORDER,
                                 row_rect, width=1, border_radius=10)

            # Show pattern > replacement
            if sel and self._dict_editing == "pattern":
                pat_txt = self._dict_edit_buf + "|"
            else:
                pat_txt = pattern
            if sel and self._dict_editing == "replacement":
                rep_txt = self._dict_edit_buf + "|"
            else:
                rep_txt = replacement

            arrow_surf = self.font_sm.render("  >  ", True, COL_TEXT_MUTED)
            pat_surf = self.font_sm.render(pat_txt, True, COL_ACCENT if (sel and self._dict_editing == "pattern") else COL_TEXT)
            rep_surf = self.font_sm.render(rep_txt, True, COL_ACCENT if (sel and self._dict_editing == "replacement") else COL_TEXT_MUTED)

            cy = row_rect.centery
            self.screen.blit(pat_surf, (row_rect.x + 12, cy - pat_surf.get_height() // 2))
            ax = row_rect.x + 12 + pat_surf.get_width()
            self.screen.blit(arrow_surf, (ax, cy - arrow_surf.get_height() // 2))
            ax += arrow_surf.get_width()
            self.screen.blit(rep_surf, (ax, cy - rep_surf.get_height() // 2))

        # --- add new row / add form ---
        add_y = y0 + len(items) * BIND_ROW_H
        if self._dict_adding:
            if visible_top <= add_y + BIND_ROW_H and add_y <= visible_bot:
                add_rect = pygame.Rect(panel.x + 12, add_y, inner_w, BIND_ROW_H - 4)
                draw_rounded_rect(self.screen, (30, 30, 34), add_rect, radius=10)
                pygame.draw.rect(self.screen, COL_ACCENT, add_rect, width=1, border_radius=10)

                pat_label = "Heard: "
                rep_label = " > Correct: "
                pat_val = self._dict_add_pattern + ("|" if self._dict_add_field == "pattern" else "")
                rep_val = self._dict_add_replacement + ("|" if self._dict_add_field == "replacement" else "")

                lbl1 = self.font_sm.render(pat_label, True, COL_TEXT_MUTED)
                val1 = self.font_sm.render(pat_val, True, COL_ACCENT if self._dict_add_field == "pattern" else COL_TEXT)
                lbl2 = self.font_sm.render(rep_label, True, COL_TEXT_MUTED)
                val2 = self.font_sm.render(rep_val, True, COL_ACCENT if self._dict_add_field == "replacement" else COL_TEXT)

                cy = add_rect.centery
                cx = add_rect.x + 12
                self.screen.blit(lbl1, (cx, cy - lbl1.get_height() // 2))
                cx += lbl1.get_width()
                self.screen.blit(val1, (cx, cy - val1.get_height() // 2))
                cx += val1.get_width()
                self.screen.blit(lbl2, (cx, cy - lbl2.get_height() // 2))
                cx += lbl2.get_width()
                self.screen.blit(val2, (cx, cy - val2.get_height() // 2))
        else:
            if visible_top <= add_y + BIND_ROW_H and add_y <= visible_bot:
                self._dict_add_btn_r = pygame.Rect(panel.x + 12, add_y, inner_w, BIND_ROW_H - 4)
                hov_add = self._dict_add_btn_r.collidepoint(mx, my)
                bg_add = COL_SURFACE_HOVER if hov_add else (30, 30, 34)
                draw_rounded_rect(self.screen, bg_add, self._dict_add_btn_r, radius=10)
                pygame.draw.rect(self.screen, COL_BORDER_SUBTLE if not hov_add else COL_BORDER,
                                 self._dict_add_btn_r, width=1, border_radius=10)
                plus_surf = self.font.render("+ Add correction", True,
                                             COL_TEXT_MUTED if not hov_add else COL_TEXT)
                self.screen.blit(
                    plus_surf,
                    (self._dict_add_btn_r.centerx - plus_surf.get_width() // 2,
                     self._dict_add_btn_r.centery - plus_surf.get_height() // 2),
                )
            else:
                self._dict_add_btn_r = pygame.Rect(0, 0, 0, 0)

        # --- footer ---
        foot = pygame.Rect(16, h - 42, w - 32, 30)
        max_foot_w = foot.w - 16
        if self._dict_adding:
            msg = "Tab=switch field | Enter=save | Esc=cancel"
            self.screen.blit(self.font_sm.render(msg, True, COL_ACCENT), (foot.x + 8, foot.y + 8))
        elif self._dict_editing:
            field = "pattern" if self._dict_editing == "pattern" else "replacement"
            msg = f"Editing {field} | Enter=save | Esc=cancel | Tab=other field"
            self.screen.blit(self.font_sm.render(msg, True, COL_ACCENT), (foot.x + 8, foot.y + 8))
        else:
            msg = "Click=select | Enter=edit | Tab=replacement | Del=remove | Scroll=list"
            foot_txt = self._truncate_to_width(self.font_sm, msg, max_foot_w)
            self.screen.blit(self.font_sm.render(foot_txt, True, COL_TEXT_MUTED), (foot.x + 8, foot.y + 8))

    def _ui_dict_mouse_down(self, mx, my):
        """Handle mouse clicks in the Dictation corrections tab."""
        if self._dict_adding or self._dict_editing:
            return  # ignore clicks while editing; use keyboard
        # Click on "+ Add correction" button
        if self._dict_add_btn_r.w > 0 and self._dict_add_btn_r.collidepoint(mx, my):
            self._dict_adding = True
            self._dict_add_pattern = ""
            self._dict_add_replacement = ""
            self._dict_add_field = "pattern"
            self._dict_selected_idx = -1
            return
        # Click on a row to select it
        for i, (rect, _pat) in enumerate(self._dict_rows):
            if rect.w > 0 and rect.collidepoint(mx, my):
                self._dict_selected_idx = i
                return

    def _draw_stick(self, cx, cy, ax_x, ax_y, r=32):
        # outer ring with subtle gradient
        s = pygame.Surface((r * 2 + 4, r * 2 + 4), pygame.SRCALPHA)
        sc = r + 2
        pygame.draw.circle(s, (20, 20, 24, 255), (sc, sc), r)
        pygame.draw.circle(s, (*COL_BORDER_SUBTLE[:3], 120), (sc, sc), r, 1)
        # inner subtle ring
        pygame.draw.circle(s, (*COL_BORDER_SUBTLE[:3], 40), (sc, sc), r - 8, 1)
        self.screen.blit(s, (cx - r - 2, cy - r - 2))
        # crosshair
        ch = pygame.Surface((r * 2, r * 2), pygame.SRCALPHA)
        cr = r
        pygame.draw.line(ch, (*COL_BORDER_SUBTLE[:3], 30), (cr, 8), (cr, r * 2 - 8))
        pygame.draw.line(ch, (*COL_BORDER_SUBTLE[:3], 30), (8, cr), (r * 2 - 8, cr))
        self.screen.blit(ch, (cx - r, cy - r))
        # stick position
        x = self._read_axis_safe(ax_x)
        y = self._read_axis_safe(ax_y)
        dot_x = cx + int(x * (r - 6))
        dot_y = cy + int(y * (r - 6))
        draw_glow_circle(self.screen, (dot_x, dot_y), 5, COL_ACCENT, intensity=70)

    def _draw_trigger(self, x, y, label, axis_name):
        bar_w, bar_h = 16, 70
        raw = self._read_axis_safe(axis_name)
        fill = max(0.0, (raw + 1.0) / 2.0)
        lbl_s = self.font_sm.render(label, True, COL_TEXT_DIM)
        self.screen.blit(lbl_s, (x + bar_w // 2 - lbl_s.get_width() // 2, y - 16))
        # track
        track = pygame.Rect(x, y, bar_w, bar_h)
        draw_rounded_rect(self.screen, (20, 20, 24), track, radius=bar_w // 2)
        pygame.draw.rect(self.screen, COL_BORDER_SUBTLE, track, width=1,
                         border_radius=bar_w // 2)
        # fill with glow
        fh = int(fill * bar_h)
        if fh > 2:
            fill_r = pygame.Rect(x + 2, y + bar_h - fh, bar_w - 4, fh)
            draw_rounded_rect(self.screen, COL_ACCENT, fill_r, radius=(bar_w - 4) // 2)
            # glow at top of fill
            glow = pygame.Surface((bar_w + 8, 12), pygame.SRCALPHA)
            pygame.draw.ellipse(glow, (*COL_ACCENT[:3], 40), (0, 0, bar_w + 8, 12))
            self.screen.blit(glow, (x - 4, y + bar_h - fh - 4))

    def _discover_axes(self):
        for i in range(self.js.get_numaxes()):
            v = self.js.get_axis(i)
            if abs(v) > 0.25:
                print(f"  AXIS  idx={i}  val={v:+.3f}")

    # ---------------------------------------------------------- UI events

    def _ui_mouse_down(self, ev):
        if ev.button != 1 or self.discover:
            return
        mx, my = ev.pos
        if self.guide_overlay:
            if self._guide_close_r.collidepoint(mx, my):
                self._close_guide_overlay()
            return
        if self._tab_dash_r.collidepoint(mx, my):
            self.ui_panel = "dashboard"
            self._bind_recording_action = None
            self._dict_editing = None
            self._dict_adding = False
            self._lang_dropdown_open = False
            return
        if self._tab_bind_r.collidepoint(mx, my):
            self.ui_panel = "bindings"
            self._bind_recording_action = None
            self._dict_editing = None
            self._dict_adding = False
            self._lang_dropdown_open = False
            return
        if self._tab_dict_r.collidepoint(mx, my):
            self.ui_panel = "dictation"
            self._bind_recording_action = None
            self._dict_editing = None
            self._dict_adding = False
            self._lang_dropdown_open = False
            return
        if self.ui_panel == "dictation":
            self._ui_dict_mouse_down(mx, my)
            return
        if self.ui_panel == "dashboard":
            if self._lang_dropdown_open:
                for rect, code in self._lang_dropdown_rects:
                    if rect.collidepoint(mx, my):
                        self._set_dictation_language(code)
                        self._lang_dropdown_open = False
                        return
                self._lang_dropdown_open = False
                return
            if self._lang_chip_r.collidepoint(mx, my):
                self._lang_dropdown_open = True
                self._lang_dropdown_scroll = 0
                return
            if self._mode_chip_r.collidepoint(mx, my):
                self.mode = "CODE" if self.mode == "NORMAL" else "NORMAL"
                if self.vib_on_mode_change:
                    self._vibrate_mode_change()
                return
            if self._speed_chip_r.collidepoint(mx, my):
                self.speed_idx = (self.speed_idx + 1) % len(self.speeds)
                return
            return
        if self.ui_panel != "bindings":
            return
        if self._bind_recording_action and self._bind_recording_action in MOUSE_ACTIONS:
            for rect, spec in self._mouse_chip_rects:
                if rect.collidepoint(mx, my):
                    self._apply_shortcut_override(self._bind_recording_action, spec)
                    return
            return
        for i, (rect, _aid) in enumerate(self._bind_rows):
            if rect.w > 0 and rect.collidepoint(mx, my):
                self._bind_selected_idx = i
                return

    def _ui_mouse_wheel(self, ev):
        if self.discover:
            return
        if self.guide_overlay:
            self.guide_scroll = max(0, self.guide_scroll - ev.y * 36)
            self._clamp_guide_scroll()
            return
        if self.ui_panel == "dashboard" and self._lang_dropdown_open:
            if self._lang_dropdown_panel.collidepoint(pygame.mouse.get_pos()):
                self._lang_dropdown_scroll -= ev.y * 24
                return
        if self.ui_panel == "dictation":
            self._dict_scroll -= ev.y * (BIND_ROW_H // 2)
            self._clamp_dict_scroll()
            return
        if self.ui_panel != "bindings":
            return
        self._bind_scroll -= ev.y * (BIND_ROW_H // 2)
        self._clamp_bind_scroll()

    def _ui_key_down(self, ev):
        if self.discover:
            return
        if self.guide_overlay and ev.key == pygame.K_ESCAPE:
            self._close_guide_overlay()
            return
        if ev.key == pygame.K_ESCAPE:
            if self._bind_recording_action:
                self._bind_recording_action = None
                return
            if self._dict_adding:
                self._dict_adding = False
                return
            if self._dict_editing:
                self._dict_editing = None
                return
            return
        if self.ui_panel == "dictation":
            self._ui_dict_key_down(ev)
            return
        if self.ui_panel != "bindings":
            return
        if self._bind_recording_action:
            if self._bind_recording_action in MOUSE_ACTIONS:
                return
            ch = chord_from_event(ev)
            if ch:
                self._apply_shortcut_override(self._bind_recording_action, ch)
            return
        if ev.key == pygame.K_RETURN and self._bind_selected_idx >= 0:
            ids = self._bind_action_ids
            idx = self._bind_selected_idx
            if idx < len(ids):
                self._bind_recording_action = ids[idx]

    def _ui_dict_key_down(self, ev):
        """Handle keyboard input for the Dictation corrections tab."""
        # --- adding new entry ---
        if self._dict_adding:
            if ev.key == pygame.K_TAB:
                self._dict_add_field = "replacement" if self._dict_add_field == "pattern" else "pattern"
            elif ev.key == pygame.K_RETURN:
                if self._dict_add_pattern.strip():
                    self._save_correction(self._dict_add_pattern, self._dict_add_replacement)
                self._dict_adding = False
            elif ev.key == pygame.K_BACKSPACE:
                if self._dict_add_field == "pattern":
                    self._dict_add_pattern = self._dict_add_pattern[:-1]
                else:
                    self._dict_add_replacement = self._dict_add_replacement[:-1]
            else:
                ch = ev.unicode
                if ch and ch.isprintable():
                    if self._dict_add_field == "pattern":
                        self._dict_add_pattern += ch
                    else:
                        self._dict_add_replacement += ch
            return

        # --- editing existing entry ---
        if self._dict_editing:
            items = self._get_corrections_list()
            if self._dict_selected_idx < 0 or self._dict_selected_idx >= len(items):
                self._dict_editing = None
                return
            old_pat, old_rep = items[self._dict_selected_idx]
            if ev.key == pygame.K_TAB:
                # Save current field and switch to the other
                if self._dict_editing == "pattern":
                    new_pat = self._dict_edit_buf.strip()
                    if new_pat and new_pat != old_pat:
                        self._delete_correction(old_pat)
                        self._save_correction(new_pat, old_rep)
                    self._dict_editing = "replacement"
                    # Re-fetch after possible rename
                    items = self._get_corrections_list()
                    if self._dict_selected_idx < len(items):
                        self._dict_edit_buf = items[self._dict_selected_idx][1]
                else:
                    self._save_correction(old_pat, self._dict_edit_buf)
                    self._dict_editing = "pattern"
                    items = self._get_corrections_list()
                    if self._dict_selected_idx < len(items):
                        self._dict_edit_buf = items[self._dict_selected_idx][0]
            elif ev.key == pygame.K_RETURN:
                if self._dict_editing == "pattern":
                    new_pat = self._dict_edit_buf.strip()
                    if new_pat and new_pat != old_pat:
                        self._delete_correction(old_pat)
                        self._save_correction(new_pat, old_rep)
                    elif new_pat == old_pat:
                        pass  # no change
                else:
                    self._save_correction(old_pat, self._dict_edit_buf)
                self._dict_editing = None
            elif ev.key == pygame.K_BACKSPACE:
                self._dict_edit_buf = self._dict_edit_buf[:-1]
            else:
                ch = ev.unicode
                if ch and ch.isprintable():
                    self._dict_edit_buf += ch
            return

        # --- normal selection mode ---
        items = self._get_corrections_list()
        if ev.key == pygame.K_RETURN and 0 <= self._dict_selected_idx < len(items):
            self._dict_editing = "pattern"
            self._dict_edit_buf = items[self._dict_selected_idx][0]
        elif ev.key == pygame.K_TAB and 0 <= self._dict_selected_idx < len(items):
            self._dict_editing = "replacement"
            self._dict_edit_buf = items[self._dict_selected_idx][1]
        elif ev.key in (pygame.K_DELETE, pygame.K_BACKSPACE) and 0 <= self._dict_selected_idx < len(items):
            pat = items[self._dict_selected_idx][0]
            self._delete_correction(pat)
            if self._dict_selected_idx >= len(self._get_corrections_list()):
                self._dict_selected_idx = len(self._get_corrections_list()) - 1

    # ---------------------------------------------------------- main loop

    def run(self):
        print("─" * 52)
        if self.discover:
            print("DISCOVER MODE — press buttons / move sticks to see raw values.\n")
        else:
            print("Controls (Normal):    Left Stick = Mouse    Right Stick = Scroll")
            print("  X = Click   O = Backspace   Sq = Copy   Tr = Paste   L3 = Right-click")
            print("  L2+X = Enter   L2+O = Escape   L2+Left/Right = prev/next app window   L2+Down/Up = mux prev/next")
            print("  R2 full = Enter")
            print("  L1 + btn = Code mode   R1 (hold) = Dictation   Touchpad = AI voice")
            print("  R3 = Speed   L2+stick = precision mouse   PS = Pause controller")
            print("  Options+Share = on-screen binding guide")
            print("─" * 52)

        clock = pygame.time.Clock()
        dock_icon_frame = 0
        try:
            while self.running:
                for ev in pygame.event.get():
                    if ev.type == pygame.QUIT:
                        self.running = False

                    elif ev.type == pygame.VIDEORESIZE:
                        nw, nh = ev.dict.get("size", (640, 480))
                        self.screen = pygame.display.set_mode(
                            (max(nw, 420), max(nh, 360)),
                            pygame.RESIZABLE,
                        )
                        self._clamp_bind_scroll()
                        self._clamp_dict_scroll()
                        self._clamp_guide_scroll()

                    elif ev.type == pygame.MOUSEBUTTONDOWN:
                        self._ui_mouse_down(ev)

                    elif ev.type == pygame.MOUSEWHEEL:
                        self._ui_mouse_wheel(ev)

                    elif ev.type == pygame.KEYDOWN:
                        self._ui_key_down(ev)

                    elif ev.type == pygame.JOYBUTTONDOWN:
                        self._btn_down(ev.button)

                    elif ev.type == pygame.JOYBUTTONUP:
                        self._btn_up(ev.button)

                    elif ev.type == pygame.JOYHATMOTION:
                        self._hat_motion(*ev.value)

                    elif ev.type == pygame.JOYDEVICEREMOVED:
                        # Only react if it's *our* joystick that was removed
                        removed_id = getattr(ev, "instance_id", None)
                        if removed_id is None or removed_id == self._js_instance_id:
                            print("\n  [WARN] Controller disconnected!")
                            self.active = False
                            self._js_instance_id = None
                            self._native_rumble.close()

                    elif ev.type == pygame.JOYDEVICEADDED:
                        # SDL fires JOYDEVICEADDED at startup for every
                        # already-connected device — ignore those.
                        if time.monotonic() - self._init_time < 1.0:
                            continue
                        if self._js_instance_id is not None:
                            continue  # already have a live joystick
                        print("\n  [INFO] Controller reconnected.")
                        try:
                            self.js = pygame.joystick.Joystick(ev.device_index)
                            self.js.init()
                            self._js_instance_id = self.js.get_instance_id()
                            self.active = True
                            # Re-probe rumble for new connection
                            self._rumble_use_native = False
                            self._native_rumble.close()
                            if DualSenseRumble.available():
                                bt = detect_hid_bt()
                                self._native_rumble.probe(bluetooth=bt)
                                self._rumble_use_native = True
                        except pygame.error as e:
                            print(f"  [ERROR] Could not reinit joystick: {e}")

                self._tick_approval_prompt_vibration(time.monotonic())
                self._process_rumble_queue()

                if self.guide_overlay:
                    self._handle_guide_overlay_scroll()
                elif self.active and not self.discover:
                    self._handle_mouse()
                    self._handle_scroll()
                    self._check_r2()

                if self.discover:
                    self._discover_axes()

                self._draw()
                # Set dock icon after a few frames so SDL has fully settled.
                dock_icon_frame += 1
                if dock_icon_frame == 5:
                    self._set_dock_icon()
                clock.tick(60)

        except KeyboardInterrupt:
            print("\n\nShutting down.")
        finally:
            self._native_rumble.close()
            self.dictation.cleanup()
            pygame.quit()
