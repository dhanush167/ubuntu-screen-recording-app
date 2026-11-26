"""User settings, stored as JSON in ~/.config/screen-recorder/settings.json."""

import json
import os
import sys

from gi.repository import GLib

FRAME_RATES = (15, 24, 30)
QUALITIES = ("low", "medium", "high")
DEFAULT_HOTKEY = "<Control><Alt>r"


def config_path():
    return os.path.join(GLib.get_user_config_dir(), "screen-recorder", "settings.json")


def default_folder():
    videos = GLib.get_user_special_dir(GLib.UserDirectory.DIRECTORY_VIDEOS)
    home = os.path.expanduser("~")
    if not videos or os.path.normpath(videos) == home:
        videos = os.path.join(home, "Videos")
    return os.path.join(videos, "Recordings")


def defaults():
    return {
        "folder": default_folder(),
        "fps": 30,
        "quality": "medium",
        "hotkey": DEFAULT_HOTKEY,   # "" turns the hotkey off
        "mic_enabled": True,
        "mic_device": "",           # "" means the system default
        "system_enabled": True,
        "system_device": "",
        "monitor": "",              # X11: connector name of the chosen monitor
        "restore_token": "",        # Wayland: reuses the screen choice
        "screen_label": "",         # Wayland: what that choice was, for display
        "last_size": None,          # [width, height] of the last recording
    }


def load(path=None):
    settings = defaults()
    try:
        with open(path or config_path(), encoding="utf-8") as handle:
            stored = json.load(handle)
    except (OSError, ValueError):
        return settings
    if not isinstance(stored, dict):
        return settings
    for key, value in stored.items():
        if key not in settings:
            continue
        if key == "last_size":
            if (isinstance(value, list) and len(value) == 2
                    and all(isinstance(v, int) and v > 0 for v in value)):
                settings[key] = value
        elif type(value) is type(settings[key]):
            settings[key] = value
    if settings["fps"] not in FRAME_RATES:
        settings["fps"] = 30
    if settings["quality"] not in QUALITIES:
        settings["quality"] = "medium"
    if not settings["folder"]:
        settings["folder"] = default_folder()
    return settings


def save(settings, path=None):
    path = path or config_path()
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        temporary = path + ".tmp"
        with open(temporary, "w", encoding="utf-8") as handle:
            json.dump(settings, handle, indent=2)
        os.replace(temporary, path)
    except OSError as error:
        print(f"Could not save settings: {error}", file=sys.stderr)
