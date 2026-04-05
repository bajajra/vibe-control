# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for Vibe Control.app"""

import os
import speech_recognition as sr

with open("VERSION") as f:
    version = f.read().strip()

sr_dir = os.path.dirname(sr.__file__)

a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=[],
    datas=[
        ("config.json", "."),
        (sr_dir, "speech_recognition"),
    ],
    hiddenimports=[
        "controller_interface",
        "dictation",
        "defaults",
        "dualsense_rumble",
        "prompt_detect",
        "ui_draw",
        "keymap",
        "objc",
        "ApplicationServices",
        "pygame",
        "pyautogui",
        "pyscreeze",
        "pytweening",
        "pyperclip",
        "pymsgbox",
        "pyaudio",
        "speech_recognition",
        "Quartz",
        "AppKit",
        "Foundation",
        "hid",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib", "numpy", "scipy"],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="VibeControl",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    target_arch="arm64",
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="VibeControl",
)

app = BUNDLE(
    coll,
    name="Vibe Control.app",
    icon="VibeControl.icns",
    bundle_identifier="com.bajajra.vibecontrol",
    info_plist={
        "CFBundleName": "Vibe Control",
        "CFBundleDisplayName": "Vibe Control",
        "CFBundleIconFile": "VibeControl",
        "CFBundleVersion": version,
        "CFBundleShortVersionString": version,
        "LSMinimumSystemVersion": "12.0",
        "NSMicrophoneUsageDescription": (
            "Vibe Control needs microphone access for voice dictation "
            "(R1 / touchpad)."
        ),
        "NSHighResolutionCapable": True,
    },
)
