#!/usr/bin/env python3
"""
Entry point for Vibe Control — controller → Cursor/Claude Code interface.

Usage:
    python main.py                  # normal mode
    python main.py --discover       # print raw button/axis values for calibration
    python main.py --sensitivity 1.5
    python main.py --config my.json
"""

import argparse
import os
import shutil
import sys

from controller_interface import ControllerInterface


def resolve_config_path(cli_path: str) -> str:
    """
    PyInstaller .app: cwd is not the bundle — use bundled JSON + user Application Support.
    dev: ./config.json next to the repo.
    """
    if cli_path != "config.json":
        return os.path.abspath(cli_path)

    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        bundled = os.path.join(sys._MEIPASS, "config.json")
        app_support = os.path.expanduser("~/Library/Application Support/Vibe Control")
        os.makedirs(app_support, exist_ok=True)
        user_cfg = os.path.join(app_support, "config.json")
        if not os.path.isfile(user_cfg):
            legacy_cfg = os.path.join(
                os.path.expanduser("~/Library/Application Support/CtrlStick"),
                "config.json",
            )
            if os.path.isfile(legacy_cfg):
                shutil.copy2(legacy_cfg, user_cfg)
            elif os.path.isfile(bundled):
                shutil.copy2(bundled, user_cfg)
        if os.path.isfile(user_cfg):
            return user_cfg
        if os.path.isfile(bundled):
            return bundled
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "config.json"))


def main():
    ap = argparse.ArgumentParser(
        description="Vibe Control — map a PlayStation controller to mouse, keyboard "
                    "shortcuts, and voice dictation for Cursor IDE & Claude Code.",
    )
    ap.add_argument(
        "--discover", action="store_true",
        help="Show raw controller input (buttons, axes, hats) for mapping/calibration.",
    )
    ap.add_argument(
        "--config", default="config.json",
        help="Path to the JSON configuration file (default: config.json or app support).",
    )
    ap.add_argument(
        "--sensitivity", type=float, default=1.0,
        help="Global mouse sensitivity multiplier (default: 1.0).",
    )
    args = ap.parse_args()

    cfg_path = resolve_config_path(args.config)

    try:
        iface = ControllerInterface(
            config_path=cfg_path,
            sensitivity=args.sensitivity,
            discover=args.discover,
        )
        iface.run()
    except Exception as exc:
        print(f"\n[FATAL] {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
