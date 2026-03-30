"""
Heuristic detection of Cursor / VS Code / terminal approval prompts via macOS
Accessibility (AX). Same macOS Accessibility permission as pyautogui is required
for reliable results.
"""

from __future__ import annotations

import re
import sys
from typing import FrozenSet, List, Optional, Tuple

_STRONG = re.compile(
    r"run\s+this\s+command|run\s+command|allow\s+this|tool\s+(use|call)|"
    r"requires?\s+(your\s+)?approval|permission\s+to\s+run|"
    r"execute\s+(this\s+)?(command|shell)|approve\s+(this|execution)|"
    r"shell\s+command|pending\s+approval|"
    r"\[y/n\]|y\s*/\s*n|yes\s*/\s*no|\(\s*y\s*/\s*n\s*\)",
    re.I,
)

_BUTTON_LABEL = re.compile(
    r"^(run(\s+anyway|\s+command)?|allow|always\s+allow|yes|no|reject|deny|"
    r"skip|approve|cancel|continue|execute(\s+anyway)?)\s*$",
    re.I,
)

_TERMINAL_BUNDLES: FrozenSet[str] = frozenset({
    "com.apple.Terminal",
    "com.googlecode.iterm2",
    "dev.warp.Warp-Stable",
    "co.zeit.hyper",
    "com.github.wez.wezterm",
})


def _is_target_app(bundle_id: Optional[str], name: Optional[str]) -> bool:
    b = (bundle_id or "").lower()
    n = (name or "").lower()
    if "cursor" in b or "cursor" in n:
        return True
    if "vscode" in b or "vscodium" in b:
        return True
    if "visual studio code" in n:
        return True
    if b in _TERMINAL_BUNDLES:
        return True
    return False


def _scan_app(pid: int, max_nodes: int = 900, max_depth: int = 22) -> bool:
    from ApplicationServices import (
        AXUIElementCreateApplication,
        AXUIElementCopyAttributeValue,
        kAXChildrenAttribute,
        kAXDescriptionAttribute,
        kAXHelpAttribute,
        kAXRoleAttribute,
        kAXTitleAttribute,
        kAXValueAttribute,
    )

    root = AXUIElementCreateApplication(pid)
    texts: List[str] = []
    buttons: List[str] = []

    queue: List[Tuple[object, int]] = [(root, 0)]
    nodes = 0

    while queue and nodes < max_nodes:
        elem, depth = queue.pop(0)
        nodes += 1
        if depth > max_depth:
            continue

        err, role = AXUIElementCopyAttributeValue(elem, kAXRoleAttribute, None)
        role_s = str(role).strip() if err == 0 and role else ""

        chunks: List[str] = []
        for attr in (
            kAXTitleAttribute,
            kAXValueAttribute,
            kAXDescriptionAttribute,
            kAXHelpAttribute,
        ):
            err, val = AXUIElementCopyAttributeValue(elem, attr, None)
            if err == 0 and val:
                s = str(val).strip()
                if s:
                    if len(s) > 2000:
                        s = s[:2000]
                    chunks.append(s)

        if role_s == "AXButton":
            title = chunks[0] if chunks else ""
            if title:
                buttons.append(title)
        else:
            texts.extend(chunks)

        err, children = AXUIElementCopyAttributeValue(elem, kAXChildrenAttribute, None)
        if err != 0 or not children:
            continue
        for child in children:
            queue.append((child, depth + 1))

    blob = "\n".join(texts)
    matched = [b for b in buttons if _BUTTON_LABEL.match(b)]
    if _STRONG.search(blob):
        return True
    if len(matched) >= 2:
        return True
    if len(matched) >= 1 and re.search(
        r"\[y/n\]|\by\s*/\s*n\b|yes.*/.*no", blob, re.I
    ):
        return True
    return False


def approval_prompt_active() -> bool:
    """True if the frontmost app is Cursor/VS Code/a terminal and AX looks like a prompt."""
    if sys.platform != "darwin":
        return False
    try:
        from AppKit import NSWorkspace
    except Exception:
        return False

    app = NSWorkspace.sharedWorkspace().frontmostApplication()
    if app is None:
        return False
    if not _is_target_app(app.bundleIdentifier(), app.localizedName()):
        return False
    try:
        return _scan_app(app.processIdentifier())
    except Exception:
        return False
