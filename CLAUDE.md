# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Vibe Control** is a macOS app that turns a PlayStation DualSense controller (USB) into a full input device for Cursor IDE, Claude Code, and terminal workflows — mouse, scrolling, IDE shortcuts, haptic feedback, and voice dictation.

## Commands

```bash
# Run from source (requires DualSense connected via USB)
brew install portaudio          # needed for PyAudio
pip install -r requirements.txt
python main.py

# Calibration mode (print raw button/axis indices)
python main.py --discover

# Build macOS .app bundle
pip install "pyinstaller>=6.0"
pyinstaller VibeControl.spec --noconfirm
# Output: dist/Vibe Control.app
```

There are no tests or linting configured in this project.

## Architecture

The app is a single-process Python program using **pygame** for the event loop and UI, **pyautogui** for simulating mouse/keyboard, and **PyAudio + SpeechRecognition** for voice dictation.

### Key modules

- **`main.py`** — Entry point. Parses CLI args, resolves config path (handles PyInstaller bundle vs dev), creates `ControllerInterface` and calls `run()`.
- **`controller_interface.py`** — Core class (`ControllerInterface`). Contains the pygame event loop, joystick handling, button→action dispatch, two input modes (Normal/Code toggled by L1), mouse/scroll movement, UI rendering (tabs: Status, Bindings), shortcut override editing, and approval-prompt vibration loop.
- **`defaults.py`** — `DEFAULT_CONFIG` dict with all default button mappings, mouse/scroll/dictation/vibration/mux settings. Provides `deep_merge()` to overlay user `config.json` on top of defaults.
- **`dictation.py`** — `DictationHandler` class. Records audio via PyAudio while R1 is held, transcribes on release via Google Speech Recognition, pastes result via `pbcopy` + Cmd+V.
- **`prompt_detect.py`** — `approval_prompt_active()` function. Uses macOS Accessibility APIs (AX) to scan the frontmost app's UI tree for approval/run prompts (Cursor, VS Code, terminals). Drives the haptic pulse feature.
- **`ui_draw.py`** — Drawing primitives (gradients, rounded rects, pills, search bar) using pygame. Defines the color palette (dark + neon red).
- **`keymap.py`** — Converts pygame key events to pyautogui key names; formats key chords for display.

### Config system

User config (`config.json`) is deep-merged over `DEFAULT_CONFIG` from `defaults.py`. In the packaged `.app`, config lives at `~/Library/Application Support/Vibe Control/config.json` (seeded from the bundle on first run). Sections: `mouse`, `scroll`, `dictation`, `vibration`, `mux`, `shortcut_overrides`, `button_indices`, `axis_indices`, `normal_mode`, `code_mode`.

### Two input modes

- **Normal mode** (default): left stick = mouse, buttons = click/copy/paste/arrows
- **Code mode** (hold L1): left stick = arrow keys, buttons = IDE navigation (go to def, find, tabs, terminal)

Global chords (L2+Cross = Enter, L2+Circle = Escape) work in both modes and even when paused.

### Build & distribution

- **`VibeControl.spec`** — PyInstaller spec targeting arm64 macOS
- **`setup.py`** — Alternative py2app build script
- **`.github/workflows/build-dmg.yml`** — CI: builds .app, creates DMG, publishes to GitHub Releases on version tags (`v*`)
