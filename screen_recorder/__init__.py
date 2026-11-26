"""Screen Recorder: record screen and audio to MP4 (GTK4 + GStreamer)."""

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("Gdk", "4.0")
gi.require_version("Gst", "1.0")

from gi.repository import Gst  # noqa: E402

Gst.init(None)

# Load the display-system bindings before any window exists, so window
# objects come with their Wayland/X11 methods (used to place dialogs).
for _namespace in ("GdkWayland", "GdkX11"):
    try:
        gi.require_version(_namespace, "4.0")
        __import__("gi.repository." + _namespace)
    except (ImportError, ValueError):
        pass

APP_ID = "io.github.local.ScreenRecorder"
APP_NAME = "Screen Recorder"
__version__ = "1.0.0"
