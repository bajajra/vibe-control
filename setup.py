"""
py2app build script — produces Vibe Control.app

Usage:
    python setup.py py2app
"""

from setuptools import setup

APP = ["main.py"]
DATA_FILES = [("", ["config.json"])]

OPTIONS = {
    "argv_emulation": False,
    "iconfile": "VibeControl.icns",
    "plist": {
        "CFBundleName": "Vibe Control",
        "CFBundleDisplayName": "Vibe Control",
        "CFBundleIconFile": "VibeControl",
        "CFBundleIdentifier": "com.bajajra.vibecontrol",
        "CFBundleVersion": "1.0.0",
        "CFBundleShortVersionString": "1.0",
        "LSMinimumSystemVersion": "12.0",
        "NSMicrophoneUsageDescription": (
            "Vibe Control needs microphone access "
            "for voice dictation (R1 / touchpad)."
        ),
        "NSAppleEventsUsageDescription": (
            "Vibe Control needs accessibility access "
            "to move the mouse and send keyboard shortcuts."
        ),
        "LSUIElement": False,
    },
    "packages": [
        "pygame",
        "speech_recognition",
    ],
    "includes": [
        "controller_interface",
        "dictation",
        "defaults",
        "dualsense_rumble",
        "prompt_detect",
        "ui_draw",
        "keymap",
        "pyautogui",
        "pyaudio",
        "pyscreeze",
        "pytweening",
        "pymsgbox",
        "pyperclip",
        "hid",
    ],
}

setup(
    app=APP,
    name="Vibe Control",
    data_files=DATA_FILES,
    options={"py2app": OPTIONS},
    setup_requires=["py2app"],
)
