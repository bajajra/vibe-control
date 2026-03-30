"""
Vibe Control — PlayStation controller interface for macOS
Maps joysticks to mouse/scroll, buttons to IDE shortcuts, R1 to dictation.
"""

import os
import sys
import time
import math
import json
import subprocess

import pygame
import pyautogui

from dictation import DictationHandler
from defaults import DEFAULT_CONFIG, deep_merge
from prompt_detect import approval_prompt_active
from ui_draw import (
    COL_ACCENT,
    COL_BORDER,
    COL_BG_TOP,
    COL_BG_BOT,
    COL_DANGER,
    COL_SUCCESS,
    COL_SURFACE,
    COL_SURFACE_HOVER,
    COL_TEXT,
    COL_TEXT_MUTED,
    draw_pill,
    draw_rounded_rect,
    draw_rounded_rect_alpha,
    draw_search_bar,
    draw_vertical_gradient,
)
from keymap import chord_from_event, format_chord

pyautogui.PAUSE = 0
pyautogui.FAILSAFE = True  # move mouse to top-left corner to abort

SPEED_LABELS = ["SLOW", "MEDIUM", "FAST"]

MOUSE_ACTIONS = frozenset({"left_click", "right_click", "double_click"})

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
    "next_app_window": "Next window (same app · ⌘`)",
    "prev_app_window": "Previous window (same app · ⌘⇧`)",
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
        self._bind_rows = []
        self._mouse_chip_rects = []

        self._init_pygame()

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

    def _save_config(self):
        try:
            with open(self.config_path, "w") as f:
                json.dump(self.cfg, f, indent=4)
                f.write("\n")
        except OSError as exc:
            print(f"[WARN] Could not save config: {exc}")

    def _mux_send(self, key: str):
        """Send tmux/screen-style prefix key then a command key (default Ctrl+b)."""
        mux = self.cfg.get("mux", {}) or {}
        if not mux.get("enabled", True):
            return
        mods = tuple(mux.get("prefix_mod", ["control"]))
        pk = str(mux.get("prefix_key", "b"))
        delay = float(mux.get("after_prefix_delay_s", 0.05))
        pyautogui.hotkey(*mods, pk)
        time.sleep(delay)
        pyautogui.press(key)

    def _fire_action(self, name: str):
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
        if len(spec) == 1:
            pyautogui.press(spec[0])
        else:
            pyautogui.hotkey(*spec)

    def _init_pygame(self):
        os.environ["SDL_VIDEO_ALLOW_SCREENSAVER"] = "1"
        # Critical: keep receiving joystick events even when window is not focused
        os.environ["SDL_JOYSTICK_ALLOW_BACKGROUND_EVENTS"] = "1"
        pygame.init()
        pygame.joystick.init()

        self.screen = pygame.display.set_mode((600, 480), pygame.RESIZABLE)
        pygame.display.set_caption("Vibe Control")
        self.font = pygame.font.SysFont("helveticaneue", 15)
        self.font_lg = pygame.font.SysFont("helveticaneue", 19, bold=True)
        self.font_sm = pygame.font.SysFont("helveticaneue", 13)
        self.font_mono = pygame.font.SysFont("menlo", 12)

        if pygame.joystick.get_count() == 0:
            print("[ERROR] No controller detected. Plug in your controller and retry.")
            pygame.quit()
            sys.exit(1)

        self.js = pygame.joystick.Joystick(0)
        self.js.init()
        self._js_instance_id = self.js.get_instance_id()
        self._init_time = time.monotonic()
        name = self.js.get_name()
        nb, na, nh = self.js.get_numbuttons(), self.js.get_numaxes(), self.js.get_numhats()
        print(f"[OK] {name}  (buttons={nb}  axes={na}  hats={nh})")
        if nh == 0:
            print("     D-pad mapped as buttons (no hats)")

        # Rumble queue: list of (fire_at_monotonic, low, high, duration_ms)
        # Processed on the main thread each frame — SDL is NOT thread-safe.
        self._rumble_queue = []

        if self.vib_on_startup:
            self._queue_rumble_pattern([
                (0.0,  0.5, 0.5, 150),
                (0.25, 0.7, 0.7, 200),
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
        """Gentle alternating rumble while an approval / run prompt seems visible."""
        if (
            not self.vib_enabled
            or not self.vib_on_approval_prompt
            or self.discover
        ):
            self._approval_prompt_active = False
            return
        if now - self._approval_scan_t >= self.approval_scan_interval_s:
            self._approval_scan_t = now
            try:
                self._approval_prompt_active = approval_prompt_active()
            except Exception:
                self._approval_prompt_active = False
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
        if self.discover:
            print(f"  BTN DOWN  idx={idx}  name={name}")
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
        if self.discover:
            print(f"  HAT  x={hx}  y={hy}")
            return

        new = {"up": hy == 1, "down": hy == -1, "left": hx == -1, "right": hx == 1}
        for d in ("up", "down", "left", "right"):
            if new[d] and not self._dpad[d]:
                self._dpad_press(d)
        self._dpad = new

    def _dpad_press(self, direction):
        # Normal mode only: L2 + D-pad hops Terminal windows (⌘`) / tmux panes (prefix+n/p).
        # Skipped in code mode so L2 + D-pad still maps to IDE shortcuts.
        if (
            not self.l1_held
            and self._l2_chord_gate()
            and direction in ("left", "right", "up", "down")
        ):
            mux = self.cfg.get("mux", {}) or {}
            next_k = str(mux.get("next_window_key", "n"))
            prev_k = str(mux.get("prev_window_key", "p"))
            if direction == "left" and not self._throttled("l2_dpad_prev_win", 350):
                self._fire_action("prev_app_window")
            elif direction == "right" and not self._throttled("l2_dpad_next_win", 350):
                self._fire_action("next_app_window")
            elif direction == "down" and not self._throttled("l2_dpad_mux_next", 350):
                self._mux_send(next_k)
            elif direction == "up" and not self._throttled("l2_dpad_mux_prev", 350):
                self._mux_send(prev_k)
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
        else:
            self._draw_dashboard()
        pygame.display.flip()

    def _layout_tabs(self, w, margin=20):
        y = 16
        pill_h = 34
        self._tab_dash_r = pygame.Rect(margin, y, 118, pill_h)
        self._tab_bind_r = pygame.Rect(margin + 126, y, 118, pill_h)

    def _bindings_list_geometry(self):
        w, h = self.screen.get_size()
        list_top = 58 + 52 + 10
        list_h = max(100, h - list_top - 56)
        inner_w = w - 32
        return list_top, list_h, inner_w

    def _clamp_bind_scroll(self):
        _, list_h, _ = self._bindings_list_geometry()
        row_h = 44
        n = len(self._bind_action_ids)
        max_s = max(0, n * row_h - list_h + 24)
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
        draw_pill(self.screen, self.font_sm, "Shortcuts", self._tab_bind_r, hover=hov_b)

        # --- main card ---
        panel = pygame.Rect(16, 62, w - 32, h - 78)
        draw_rounded_rect_alpha(self.screen, COL_SURFACE, panel, radius=14, alpha=240)
        pygame.draw.rect(self.screen, COL_BORDER, panel, width=1, border_radius=14)
        px, py = panel.x + 24, panel.y

        # row 1: title + paused badge
        title = self.font_lg.render("Vibe Control", True, COL_ACCENT)
        self.screen.blit(title, (px, py + 16))
        sub = self.font_sm.render("PS controller → Cursor & macOS", True, COL_TEXT_MUTED)
        self.screen.blit(sub, (px, py + 40))

        if not self.active:
            badge = pygame.Rect(panel.right - 100, py + 16, 74, 26)
            draw_rounded_rect_alpha(self.screen, COL_DANGER, badge, 8, 50)
            pygame.draw.rect(self.screen, COL_DANGER, badge, width=1, border_radius=8)
            p = self.font_sm.render("PAUSED", True, COL_DANGER)
            self.screen.blit(p, (badge.x + 10, badge.y + 5))

        # --- divider ---
        div_y = py + 62
        pygame.draw.line(self.screen, COL_BORDER, (px, div_y), (panel.right - 24, div_y))

        # row 2: mode + speed chips
        chip_y = div_y + 12
        mode_c = COL_ACCENT if self.mode == "NORMAL" else (200, 60, 80)
        mode_r = pygame.Rect(px, chip_y, 100, 28)
        draw_rounded_rect(self.screen, (40, 12, 18), mode_r, 6)
        pygame.draw.rect(self.screen, mode_c, mode_r, width=1, border_radius=6)
        self.screen.blit(self.font_sm.render(self.mode, True, mode_c), (mode_r.x + 10, mode_r.y + 6))

        spd_r = pygame.Rect(px + 110, chip_y, 90, 28)
        draw_rounded_rect(self.screen, (30, 30, 34), spd_r, 6)
        pygame.draw.rect(self.screen, COL_BORDER, spd_r, width=1, border_radius=6)
        self.screen.blit(
            self.font_sm.render(SPEED_LABELS[self.speed_idx], True, COL_TEXT_MUTED),
            (spd_r.x + 10, spd_r.y + 6),
        )

        # --- sticks + triggers section ---
        sec_y = chip_y + 44
        stick_r = 32
        gap = 40

        # left stick
        ls_cx = px + stick_r + 8
        ls_cy = sec_y + stick_r + 14
        self.screen.blit(
            self.font_sm.render("Mouse", True, COL_TEXT_MUTED),
            (ls_cx - self.font_sm.size("Mouse")[0] // 2, sec_y),
        )
        self._draw_stick(ls_cx, ls_cy, "left_x", "left_y", stick_r)

        # right stick
        rs_cx = ls_cx + stick_r * 2 + gap + stick_r
        rs_cy = ls_cy
        self.screen.blit(
            self.font_sm.render("Scroll", True, COL_TEXT_MUTED),
            (rs_cx - self.font_sm.size("Scroll")[0] // 2, sec_y),
        )
        self._draw_stick(rs_cx, rs_cy, "right_x", "right_y", stick_r)

        # triggers — right-aligned
        trig_x = panel.right - 90
        trig_y = sec_y
        self._draw_trigger(trig_x, trig_y + 14, "L2", "l2_trigger")
        self._draw_trigger(trig_x + 40, trig_y + 14, "R2", "r2_trigger")

        # --- mic bar ---
        mic_y = max(ls_cy + stick_r + 20, sec_y + 94)
        mic_box = pygame.Rect(px, mic_y, panel.w - 48, 38)
        draw_rounded_rect(self.screen, (18, 18, 22), mic_box, radius=10)
        pygame.draw.rect(self.screen, COL_BORDER, mic_box, width=1, border_radius=10)
        recording = "RECORD" in self.dictation_status
        dot_c = COL_ACCENT if recording else COL_TEXT_MUTED
        pygame.draw.circle(self.screen, dot_c, (mic_box.x + 16, mic_box.centery), 5)
        if recording:
            pygame.draw.circle(self.screen, (*COL_ACCENT[:3], 40), (mic_box.x + 16, mic_box.centery), 10)
        lbl = "RECORDING …" if recording else f"Mic · {self.dictation_status}"
        self.screen.blit(self.font.render(lbl, True, COL_TEXT), (mic_box.x + 32, mic_box.y + 10))

        # --- hint footer ---
        foot_y = panel.bottom - 34
        hints = (
            "L2+X/O = Enter/Esc · L2+◀▶ = win · L2+▼▲ = mux · "
            "Touchpad = AI · R1 = mic · L1 = code · PS = pause"
        )
        self.screen.blit(self.font_sm.render(hints, True, COL_TEXT_MUTED), (px, foot_y))

    def _draw_bindings(self):
        w, h = self.screen.get_size()
        mx, my = pygame.mouse.get_pos()
        draw_vertical_gradient(self.screen, w, h, COL_BG_TOP, COL_BG_BOT)

        self._layout_tabs(w)
        hov_d = self._tab_dash_r.collidepoint(mx, my)
        draw_pill(self.screen, self.font_sm, "Dashboard", self._tab_dash_r, active=False, hover=hov_d)
        draw_pill(self.screen, self.font_sm, "Shortcuts", self._tab_bind_r, active=True, hover=False)

        head = pygame.Rect(16, 58, w - 32, 52)
        draw_search_bar(self.screen, self.font, head, "Keyboard shortcuts", "Customize chords · saved to config")
        pygame.draw.rect(self.screen, COL_BORDER, head, width=1, border_radius=12)

        list_top, list_h, _ = self._bindings_list_geometry()
        panel = pygame.Rect(16, list_top, w - 32, list_h)
        draw_rounded_rect_alpha(self.screen, COL_SURFACE, panel, radius=14, alpha=235)
        pygame.draw.rect(self.screen, COL_BORDER, panel, width=1, border_radius=14)

        row_h = 44
        inner_w = panel.w - 24
        self._bind_rows = []
        y0 = panel.y + 8 - self._bind_scroll
        visible_top = panel.y + 8
        visible_bot = panel.bottom - 8

        for idx, aid in enumerate(self._bind_action_ids):
            ry = y0 + idx * row_h
            if ry + row_h < visible_top or ry > visible_bot:
                self._bind_rows.append((pygame.Rect(0, 0, 0, 0), aid))
                continue
            row_rect = pygame.Rect(panel.x + 12, ry, inner_w, row_h - 4)
            self._bind_rows.append((row_rect, aid))
            sel = idx == self._bind_selected_idx
            hov = row_rect.collidepoint(mx, my) and not self._bind_recording_action
            bg = COL_ACCENT if sel else (COL_SURFACE_HOVER if hov else (34, 34, 38))
            draw_rounded_rect(self.screen, bg, row_rect, radius=10, width=0)
            pygame.draw.rect(
                self.screen,
                COL_ACCENT if sel else COL_BORDER,
                row_rect,
                width=1,
                border_radius=10,
            )

            label = ACTION_LABELS.get(aid, aid.replace("_", " ").title())
            self.screen.blit(self.font.render(label, True, COL_TEXT), (row_rect.x + 12, row_rect.y + 10))

            spec = self.shortcuts.get(aid, ())
            if spec == ("click",):
                chord_txt = "Left click"
            elif spec == ("rightClick",):
                chord_txt = "Right click"
            elif spec == ("doubleClick",):
                chord_txt = "Double click"
            else:
                chord_txt = format_chord(spec)
            surf = self.font_mono.render(chord_txt, True, COL_TEXT_MUTED)
            self.screen.blit(surf, (row_rect.right - surf.get_width() - 12, row_rect.y + 11))

        foot = pygame.Rect(16, h - 42, w - 32, 30)
        if self._bind_recording_action:
            aid = self._bind_recording_action
            lab = ACTION_LABELS.get(aid, aid)
            msg = f"Press a key combination…  Enter — save · Esc — cancel   ({lab})"
            if aid in MOUSE_ACTIONS:
                msg = f"Click Left / Right / Double below · Esc — cancel   ({lab})"
            self.screen.blit(self.font_sm.render(msg, True, COL_ACCENT), (foot.x + 8, foot.y + 8))
            if aid in MOUSE_ACTIONS:
                self._draw_mouse_chips(foot.x + 8, foot.y - 36)
        else:
            self.screen.blit(
                self.font_sm.render(
                    "Click a row to select · Enter — record shortcut · Scroll wheel — list",
                    True,
                    COL_TEXT_MUTED,
                ),
                (foot.x + 8, foot.y + 8),
            )

        rec = self._bind_recording_action
        if rec and rec not in MOUSE_ACTIONS:
            overlay = pygame.Rect(w // 2 - 140, 110, 280, 36)
            draw_rounded_rect_alpha(self.screen, (20, 20, 24), overlay, 12, 230)
            pygame.draw.rect(self.screen, COL_ACCENT, overlay, width=1, border_radius=12)
            self.screen.blit(self.font_sm.render("Listening for keys…", True, COL_TEXT), (overlay.x + 16, overlay.y + 10))

    def _draw_mouse_chips(self, x, y):
        labels = [("Left", ("click",)), ("Right", ("rightClick",)), ("Double", ("doubleClick",))]
        self._mouse_chip_rects = []
        cx = x
        for lab, spec in labels:
            r = pygame.Rect(cx, y, 76, 28)
            self._mouse_chip_rects.append((r, spec))
            draw_rounded_rect(self.screen, COL_SURFACE_HOVER, r, 8, 0)
            pygame.draw.rect(self.screen, COL_BORDER, r, width=1, border_radius=8)
            self.screen.blit(self.font_sm.render(lab, True, COL_TEXT), (cx + 14, y + 6))
            cx += 84

    def _draw_stick(self, cx, cy, ax_x, ax_y, r=32):
        pygame.draw.circle(self.screen, COL_BORDER, (cx, cy), r, 1)
        pygame.draw.circle(self.screen, (26, 26, 30), (cx, cy), r - 1)
        x = self._read_axis_safe(ax_x)
        y = self._read_axis_safe(ax_y)
        dot_x = cx + int(x * (r - 6))
        dot_y = cy + int(y * (r - 6))
        # glow
        glow_s = pygame.Surface((20, 20), pygame.SRCALPHA)
        pygame.draw.circle(glow_s, (*COL_ACCENT[:3], 60), (10, 10), 10)
        self.screen.blit(glow_s, (dot_x - 10, dot_y - 10))
        pygame.draw.circle(self.screen, COL_ACCENT, (dot_x, dot_y), 5)

    def _draw_trigger(self, x, y, label, axis_name):
        bar_w, bar_h = 14, 70
        raw = self._read_axis_safe(axis_name)
        fill = max(0.0, (raw + 1.0) / 2.0)
        self.screen.blit(self.font_sm.render(label, True, COL_TEXT_MUTED), (x, y - 16))
        pygame.draw.rect(self.screen, (26, 26, 30), (x, y, bar_w, bar_h), border_radius=4)
        pygame.draw.rect(self.screen, COL_BORDER, (x, y, bar_w, bar_h), width=1, border_radius=4)
        fh = int(fill * bar_h)
        if fh > 0:
            pygame.draw.rect(
                self.screen, COL_ACCENT,
                (x + 1, y + bar_h - fh, bar_w - 2, fh),
                border_radius=3,
            )

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
        if self._tab_dash_r.collidepoint(mx, my):
            self.ui_panel = "dashboard"
            self._bind_recording_action = None
            return
        if self._tab_bind_r.collidepoint(mx, my):
            self.ui_panel = "bindings"
            self._bind_recording_action = None
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
        if self.discover or self.ui_panel != "bindings":
            return
        self._bind_scroll -= ev.y * 28
        self._clamp_bind_scroll()

    def _ui_key_down(self, ev):
        if self.discover:
            return
        if ev.key == pygame.K_ESCAPE:
            if self._bind_recording_action:
                self._bind_recording_action = None
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

    # ---------------------------------------------------------- main loop

    def run(self):
        print("─" * 52)
        if self.discover:
            print("DISCOVER MODE — press buttons / move sticks to see raw values.\n")
        else:
            print("Controls (Normal):    Left Stick = Mouse    Right Stick = Scroll")
            print("  X = Click   O = Backspace   □ = Copy   △ = Paste   L3 = Right-click")
            print("  L2+X = Enter   L2+O = Escape   L2+◀▶ = prev/next app window   L2+▼▲ = mux prev/next")
            print("  R2 full = Enter")
            print("  L1 + btn = Code mode   R1 (hold) = Dictation   Touchpad = AI voice")
            print("  R3 = Speed   L2+stick = precision mouse   PS = Pause controller")
            print("─" * 52)

        clock = pygame.time.Clock()
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
                        except pygame.error as e:
                            print(f"  [ERROR] Could not reinit joystick: {e}")

                self._tick_approval_prompt_vibration(time.monotonic())
                self._process_rumble_queue()

                if self.active and not self.discover:
                    self._handle_mouse()
                    self._handle_scroll()
                    self._check_r2()

                if self.discover:
                    self._discover_axes()

                self._draw()
                clock.tick(60)

        except KeyboardInterrupt:
            print("\n\nShutting down.")
        finally:
            self.dictation.cleanup()
            pygame.quit()
