"""The global start/stop shortcut, registered as a GNOME custom keybinding.

Ubuntu 24.04 has no global-shortcut portal, and Wayland does not let apps grab
keys, so GNOME itself runs "screen-recorder --toggle" when the keys are pressed.
"""

import os
import shlex

from gi.repository import Gio

LIST_SCHEMA = "org.gnome.settings-daemon.plugins.media-keys"
ITEM_SCHEMA = LIST_SCHEMA + ".custom-keybinding"
PATH = ("/org/gnome/settings-daemon/plugins/media-keys/"
        "custom-keybindings/screen-recorder/")


def command():
    program = os.environ.get("SCREEN_RECORDER_CMD", "screen-recorder")
    return f"{shlex.quote(program)} --toggle"


def supported():
    source = Gio.SettingsSchemaSource.get_default()
    return bool(source and source.lookup(LIST_SCHEMA, True))


def apply(accelerator):
    """Register `accelerator` (e.g. "<Control><Alt>r"); "" removes it."""
    if not supported():
        return False
    keys = Gio.Settings.new(LIST_SCHEMA)
    paths = list(keys.get_strv("custom-keybindings"))
    item = Gio.Settings.new_with_path(ITEM_SCHEMA, PATH)
    if accelerator:
        item.set_string("name", "Screen Recorder: start/stop")
        item.set_string("command", command())
        item.set_string("binding", accelerator)
        if PATH not in paths:
            keys.set_strv("custom-keybindings", paths + [PATH])
    else:
        if PATH in paths:
            keys.set_strv("custom-keybindings", [p for p in paths if p != PATH])
        for name in ("name", "command", "binding"):
            item.reset(name)
    Gio.Settings.sync()
    return True


def conflict(accelerator):
    """Name of another custom shortcut using these keys, or None."""
    if not supported() or not accelerator:
        return None
    for path in Gio.Settings.new(LIST_SCHEMA).get_strv("custom-keybindings"):
        if path == PATH:
            continue
        item = Gio.Settings.new_with_path(ITEM_SCHEMA, path)
        if item.get_string("binding").lower() == accelerator.lower():
            return item.get_string("name") or "another shortcut"
    return None
