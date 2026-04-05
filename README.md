<p align="center">
  <img
    src="https://raw.githubusercontent.com/bajajra/vibe-control/main/vibecontrol_logo.png"
    alt="Vibe Control logo"
    width="220"
  />
</p>

# Vibe Control

**Vibe Control** turns a **PlayStation DualSense** (USB) into a full input device for **macOS**, **Cursor**, and terminal workflows such as **Claude Code**: mouse, scrolling, IDE shortcuts, optional **haptics**, and **voice dictation**—without leaving the controller.

---

## Features

| Area | What you get |
|------|----------------|
| **Pointer & scroll** | Left stick moves the cursor; right stick scrolls vertically and horizontally. **L2** (held) slows the pointer for precision. |
| **Normal vs Code mode** | Hold **L1** for **Code mode** (arrow-driven navigation, symbols, tabs, AI shortcuts). Release for **Normal mode** (mouse-first, editing shortcuts). |
| **Prompt chords** | **L2 + Cross (X)** sends **Enter** (e.g. “Run” in approval dialogs). **L2 + Circle (O)** sends **Escape**. These work even when the controller is **paused** (**PS**), so you can answer Cursor prompts quickly. |
| **Terminal / mux** | **Normal mode** + **L2** + **D-pad ◀/▶**: cycle **windows** of the front app (**⌘\`**). **L2** + **▼/▲**: **tmux** prev/next window (default **Ctrl+b** **n**/**p**, configurable). |
| **Voice dictation** | Hold **R1** to record; release to transcribe with **Google Speech Recognition** and **paste** into the focused app (`pbcopy` + Cmd+V). |
| **AI chat shortcut** | **Touchpad** (normal mode): opens **AI chat** (Cmd+L), then records like dictation; on release, pastes the transcript and presses **Enter** to send. |
| **Speed presets** | **R3** cycles mouse speed **Slow → Medium → Fast**. Tweak numbers in config. |
| **Controller vibration** | Short pulses on **startup**, **dictation start/stop**, **mode change**, and a **soft alternating pulse** while macOS thinks an **approval / run** dialog is open in Cursor, VS Code, or common terminals (heuristic via Accessibility). All toggled in config. |
| **In-app Bindings** | **Bindings** tab: each row shows **controller combos** and the **keystroke** they send; edit chords via **`shortcut_overrides`** in `config.json`. |
| **On-screen guide** | **Options + Share** toggles a scrollable binding reference overlay (○ / PS / Esc / Close to dismiss). |
| **Calibration** | **`--discover`** prints raw button/axis indices for non-standard mappings. |
| **Packaged app** | PyInstaller **`Vibe Control.app`**: config lives in **`~/Library/Application Support/Vibe Control/config.json`** (seeded from the bundle on first run). Older **CtrlStick** config is copied once if present. |

---

## Requirements

- **macOS** (project tested with Apple Silicon builds; spec targets `arm64`).
- **DualSense over USB** (recommended; Bluetooth can be fussier with SDL/pygame).
- **Internet** for default **Google** dictation (change engine in config if you add another backend).
- **Permissions** (see below): **Accessibility** (control mouse/keyboard + read UI for approval heuristics) and **Microphone** (dictation).

---

## Installation & usage

### Option A — Download the prebuilt DMG

Prebuilt **Apple Silicon (arm64)** DMGs are available on the [**Releases**](https://github.com/bajajra/vibe-control/releases) page.

| Release | DMG filename | When it's built |
|---------|-------------|-----------------|
| **Tagged release** (e.g. `v0.1`) | `vibe-control-0.1.dmg` | When a version tag is pushed |
| **Latest (rolling)** | `vibe-control-latest.dmg` | Every time code is merged to `main` |

#### How to install

1. Go to [**Releases**](https://github.com/bajajra/vibe-control/releases) and download the DMG (e.g. `vibe-control-0.1.dmg`).
2. Open the DMG — you'll see **Vibe Control.app** and an **Applications** shortcut.
3. Drag **Vibe Control.app** into **Applications**.
4. Eject the DMG.
5. Open **Vibe Control** from Applications (or Spotlight).
6. **macOS will block the first launch** ("Apple could not verify…") because the app is not code-signed. To fix this, run once in Terminal:
   ```bash
   xattr -cr /Applications/Vibe\ Control.app
   ```
   Then open the app normally. Alternatively:
   - **Right-click** the app → **Open** → **Open** in the dialog, or
   - Go to **System Settings → Privacy & Security**, scroll down to find the blocked message for Vibe Control, and click **Open Anyway**.

#### Required permissions

After first launch, grant these in **System Settings → Privacy & Security**:

- **Accessibility** → enable **Vibe Control** (mouse/keyboard control + approval-prompt detection).
- **Microphone** → enable **Vibe Control** (voice dictation).

> **Intel Macs:** the prebuilt DMG targets **arm64** only. Build locally from source (Option B) or change `target_arch` in `VibeControl.spec` to `x86_64` or `universal2`.

### Option B — Run from source (developers)

```bash
# Audio capture (needed for `pip install pyaudio` on many Macs)
brew install portaudio

pip install -r requirements.txt

# Plug in the controller via USB, then:
python main.py
```

Optional flags:

```text
python main.py --discover          # calibration: print raw buttons/axes/hats
python main.py --config path.json  # custom config
python main.py --sensitivity 1.2   # mouse sensitivity multiplier
```

### Option C — Build macOS app locally (PyInstaller)

```bash
pyinstaller VibeControl.spec --noconfirm
```

Output: **`dist/Vibe Control.app`**. Put that in **Applications**, or wrap it in a **DMG** for distribution.

**Editing settings in the `.app`**

Edit:

`~/Library/Application Support/Vibe Control/config.json`

The app merges with built-in defaults, so missing keys still get sensible defaults.

---

## How to use (quick reference)

1. **Connect** the DualSense via **USB** and launch **Vibe Control**.
2. You should feel a short **startup rumble** if vibration is enabled and the controller supports it.
3. Use **left stick** to move the mouse and **right stick** to scroll.
4. Hold **L1** when you want **Code mode** (navigation + IDE shortcuts); release for **Normal mode**.
5. Hold **R1** to **dictate** into any focused field; use **touchpad** (normal mode) for the **AI chat** + dictate + send flow.
6. When Cursor asks to **run** a command: **L2 + X** confirms; **L2 + O** cancels (**Escape**).
7. **PS** **pauses** controller-driven mouse/shortcuts (chords above still work).
8. Open the **Bindings** tab to see **DualSense → keyboard** mappings and rebind keystrokes without editing JSON (optional).

---

## Controls

Default bindings match **`config.json`** / **`defaults.py`**. You can remap via `normal_mode`, `code_mode`, and **`shortcut_overrides`**.

### Global / cross-mode (not tied to Normal/Code maps)

| Input | Action |
|--------|--------|
| **L2 + X (Cross)** | **Enter** (e.g. Run in prompts) |
| **L2 + O (Circle)** | **Escape** |
| **L2 + D-pad ◀ / ▶** (normal mode) | **Previous / next window** in the front app (**⌘⇧\`** / **⌘\`**) — e.g. several Terminal.app windows, each with Claude Code |
| **L2 + D-pad ▼ / ▲** (normal mode) | **Next / previous tmux** (or **GNU screen**) window: default **Ctrl+b** then **n** / **p** (see `mux` in config) |
| **R2** (full pull) | **Enter** (from `r2_trigger` in the active mode table) |
| **PS** | Pause / resume controller output |
| **L1** (hold) | **Code mode** while held |

### Normal mode (default)

| Input | Action |
|--------|--------|
| **Left stick** | Move mouse |
| **Right stick** | Scroll |
| **L2** (hold) | Precision / slow pointer |
| **X (Cross)** | Left click |
| **O (Circle)** | Backspace |
| **□ (Square)** | Copy (Cmd+C) |
| **△ (Triangle)** | Paste (Cmd+V) |
| **L3** | Right click |
| **R3** | Cycle mouse speed |
| **D-pad** | Arrow keys (unless **L2** is held — then see global **L2 + D-pad** row) |
| **Options** | Command palette (Cmd+Shift+P) |
| **Share** | Save file (Cmd+S) |
| **Touchpad** | Open AI chat, dictate, paste, **Enter** to send |
| **R1** (hold / release) | Dictate: record while held, transcribe & paste on release |

### Code mode (hold **L1**)

| Input | Action |
|--------|--------|
| **Left stick** | Arrow-key code navigation |
| **X** | Go to definition (F12) |
| **O** | Delete word (Option+Backspace style) |
| **□** | Find (Cmd+F) |
| **△** | Toggle terminal (Ctrl+`) |
| **D-pad Up** | Quick open (Cmd+P) |
| **D-pad Down** | Go to symbol (Cmd+Shift+O) |
| **D-pad Left** | Previous tab (Cmd+Shift+[) — also switches **tabs** in Terminal/iTerm when the terminal is focused |
| **D-pad Right** | Next tab (Cmd+Shift+]) |
| **Options** | AI chat (Cmd+L) |
| **Share** | Interrupt (Ctrl+C) |
| **Touchpad** | App switcher (Cmd+Tab) |
| **L3** | Undo (Cmd+Z) |
| **R3** | Escape |

### Multiple Claude Code sessions (tabs vs windows vs tmux)

| Goal | What to use on the controller |
|------|-------------------------------|
| **Tabs** in Terminal, iTerm, Warp, or Cursor’s editor | **Code mode** (**L1**): **D-pad ◀ / ▶** → **prev_tab / next_tab** (same as **⌘⇧[** / **⌘⇧]**). |
| **Separate OS windows** of the same app (e.g. three Terminal windows) | **Normal mode**: hold **L2** + **D-pad ◀ / ▶** → **⌘⇧\`** / **⌘\`** cycle. Rebind in **Bindings** if needed (**Next window** / **Previous window**). |
| **tmux** (or **screen**) windows *inside* one terminal tab | **Normal mode**: hold **L2** + **D-pad ▼** (next) / **▲** (prev). Default = **Ctrl+b** then **n** / **p**. Change prefix or keys under **`mux`** in `config.json`. Set **`mux.enabled`** to `false` to turn off. |

---

## Voice dictation

1. **Hold R1** (or use the **touchpad** AI flow above). Recording uses the default **input device**.
2. **Speak**.
3. **Release** → audio is sent to **Google Speech Recognition**; text is copied and **pasted** into the frontmost app.

Status appears in the app window and terminal (**RECORDING → TRANSCRIBING → IDLE**). For non‑English, set `dictation.language` in config (e.g. `"hi-IN"`).

**DMG / `.app` users:** the frozen bundle includes dictation dependencies; you still need **Microphone** permission and **network** for the default Google engine. If `pyaudio` fails in **source** installs, run `brew install portaudio` then reinstall `pyaudio`.

---

## Configuration (`config.json`)

| Section | Purpose |
|---------|---------|
| `mouse` | Sensitivity, acceleration, deadzone, speed levels |
| `scroll` | Speeds, deadzone, throttle |
| `dictation` | Engine, language |
| `vibration` | `enabled`, `on_startup`, `on_dictation`, `on_mode_change`, `on_approval_prompt`, scan/pulse intervals for approval heuristic |
| `mux` | tmux/screen-style **prefix** + **n**/**p** for **L2 + D-pad ▼/▲** (`prefix_mod`, `prefix_key`, `next_window_key`, `prev_window_key`, `enabled`) |
| `shortcut_overrides` | Per-action keyboard chords (see Bindings tab) |
| `button_indices` / `axis_indices` | Maps physical inputs to pygame indices |
| `normal_mode` / `code_mode` | Button/trigger → action IDs |

### Discover mode (wrong buttons?)

```bash
python main.py --discover
```

Press every control; use printed indices to update **`button_indices`** and **`axis_indices`**.

---

## Mouse speed presets (default)

| Level | Default px/frame (approx.) |
|-------|----------------------------|
| SLOW | 5 |
| MEDIUM | 15 |
| FAST | 35 |

Cycle with **R3** in normal mode. Editable via `mouse.speeds` in config.

---

## Troubleshooting

| Problem | What to try |
|---------|-------------|
| No controller | Use **USB**; check **System Information → USB** |
| Mouse/keys dead | **Accessibility** enabled for **Vibe Control** |
| Dictation silent | **Microphone** enabled; real input device present; internet for Google |
| Wrong buttons | `--discover` + edit `button_indices` / `axis_indices` |
| Horizontal scroll ignored | Some apps don’t accept horizontal wheel events |
| `pyaudio` won’t install (dev) | `brew install portaudio`, then `pip install pyaudio` |
| Approval vibration wrong/missing | Heuristic only; tuned in `prompt_detect.py`; disable with `vibration.on_approval_prompt` |

---

## Building artifacts

- **Spec:** [VibeControl.spec](VibeControl.spec)
- **Icon:** `VibeControl.icns` (generated from `vibecontrol_logo.png` for packaging)
