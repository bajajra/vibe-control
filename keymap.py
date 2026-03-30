"""
Map pygame key events to pyautogui key names (macOS-oriented).
"""

import pygame

# Display names for modifiers / common keys
PRETTY = {
    "command": "⌘",
    "shift": "⇧",
    "option": "⌥",
    "control": "⌃",
    "return": "↵",
    "backspace": "⌫",
    "tab": "⇥",
    "space": "Space",
    "escape": "Esc",
}


def modifiers_from_event(ev):
    mods = []
    m = ev.mod
    if m & pygame.KMOD_META:
        mods.append("command")
    if m & pygame.KMOD_SHIFT:
        mods.append("shift")
    # SDL: Option is often KMOD_ALT
    if m & pygame.KMOD_ALT:
        mods.append("option")
    if m & pygame.KMOD_CTRL:
        mods.append("control")
    return mods


def _main_key_from_event(ev):
    k = ev.key
    if k == pygame.K_RETURN or k == pygame.K_KP_ENTER:
        return "return"
    if k == pygame.K_BACKSPACE:
        return "backspace"
    if k == pygame.K_TAB:
        return "tab"
    if k == pygame.K_SPACE:
        return "space"
    if k == pygame.K_ESCAPE:
        return None
    if k == pygame.K_PERIOD:
        return "."
    if k == pygame.K_COMMA:
        return ","
    if k == pygame.K_MINUS:
        return "-"
    if k == pygame.K_EQUALS:
        return "="
    if k == pygame.K_LEFTBRACKET:
        return "["
    if k == pygame.K_RIGHTBRACKET:
        return "]"
    if k == pygame.K_BACKSLASH:
        return "\\"
    if k == pygame.K_SEMICOLON:
        return ";"
    if k == pygame.K_QUOTE:
        return "'"
    if k == pygame.K_SLASH:
        return "/"
    if k == pygame.K_BACKQUOTE:
        return "`"
    if pygame.K_F1 <= k <= pygame.K_F12:
        return f"f{k - pygame.K_F1 + 1}"
    if pygame.K_0 <= k <= pygame.K_9:
        return chr(k - pygame.K_0 + ord("0"))
    if pygame.K_a <= k <= pygame.K_z:
        return chr(k - pygame.K_a + ord("a"))
    if pygame.K_KP0 <= k <= pygame.K_KP9:
        return chr(k - pygame.K_KP0 + ord("0"))
    return None


def chord_from_event(ev):
    """Return ordered tuple of pyautogui key names, or None if not a valid chord."""
    main = _main_key_from_event(ev)
    if main is None:
        return None
    mods = modifiers_from_event(ev)
    order = ["command", "control", "option", "shift"]
    mods_sorted = [x for x in order if x in mods]
    return tuple(mods_sorted + [main])


def format_chord(chord):
    if not chord:
        return "—"
    parts = []
    for k in chord:
        parts.append(PRETTY.get(k, k.upper() if len(k) == 1 else k))
    return " ".join(parts)
