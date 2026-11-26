"""Application object, command line and notifications."""

import os
import signal
import sys

from gi.repository import Adw, Gdk, Gio, GLib, Gtk

from . import APP_ID, APP_NAME, __version__, config, hotkey
from .window import Window

CSS = """
.timer { font-size: 44px; font-weight: 300; font-feature-settings: "tnum"; }
"""


class Application(Adw.Application):
    def __init__(self, application_id=APP_ID):
        super().__init__(application_id=application_id,
                         flags=Gio.ApplicationFlags.HANDLES_COMMAND_LINE)
        self.window = None
        self.add_main_option(
            "toggle", ord("t"), GLib.OptionFlags.NONE, GLib.OptionArg.NONE,
            "Start recording, or stop the current recording", None)

    def do_startup(self):
        Adw.Application.do_startup(self)
        provider = Gtk.CssProvider()
        if hasattr(provider, "load_from_string"):  # GTK 4.12+
            provider.load_from_string(CSS)
        else:
            provider.load_from_data(CSS, -1)
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(), provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

        for name, handler in (("open-folder", self.open_folder), ("play", self.play)):
            action = Gio.SimpleAction.new(name, GLib.VariantType("s"))
            action.connect("activate",
                           lambda _a, value, run=handler: run(value.get_string()))
            self.add_action(action)

        # Logging out or Ctrl+C still finishes the file properly.
        for number in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
            GLib.unix_signal_add(GLib.PRIORITY_HIGH, number, self._on_signal)

    def do_command_line(self, command_line):
        toggle = command_line.get_options_dict().contains("toggle")
        if self.window is None:
            self.window = Window(self)
            keys = self.window.config["hotkey"]
            other = hotkey.conflict(keys)
            if other:
                self.window.toast(f"The hotkey is already used by {other}. "
                                  "Choose another in Settings.")
            else:
                hotkey.apply(keys)
            self.window.present()
            if toggle:
                self.window.toggle()
        elif toggle:
            self.window.toggle()
        else:
            self.window.present()
        return 0

    def window_closed(self):
        self.window = None
        # Its Play / Open folder buttons only work while the app is running.
        self.withdraw_notification("recording")

    def _on_signal(self):
        if self.window is None:
            self.quit()
        elif self.window.recording is not None:
            self.window.shutdown()
        else:
            self.window.close()
            self.quit()
        return True

    # -- saved files ----------------------------------------------------------

    def notify_finished(self, path, error, notice):
        if error:
            title, body = "Recording problem", error
        else:
            title, body = "Saved!", os.path.basename(path) if path else ""
            if notice:
                body = f"{notice}\n{body}"
        notification = Gio.Notification.new(title)
        notification.set_body(body)
        if path:
            target = GLib.Variant("s", path)
            notification.add_button_with_target("Open folder", "app.open-folder", target)
            notification.add_button_with_target("Play", "app.play", target)
            notification.set_default_action_and_target("app.open-folder", target)
        self.send_notification("recording", notification)

    def open_folder(self, path):
        """Show `path` selected in the file manager."""
        if not path:
            return
        if os.path.exists(path):
            Gtk.FileLauncher(file=Gio.File.new_for_path(path)).open_containing_folder(
                self.window, None, self._folder_opened)
        else:
            self._launch(os.path.dirname(path))

    def play(self, path):
        if path:
            self._launch(path)

    def _launch(self, path):
        if not os.path.exists(path):
            if self.window:
                self.window.toast("That file no longer exists")
            return
        Gtk.FileLauncher(file=Gio.File.new_for_path(path)).launch(
            self.window, None, self._launched)

    def _launched(self, launcher, result):
        self._report_launch(launcher.launch_finish, result)

    def _folder_opened(self, launcher, result):
        self._report_launch(launcher.open_containing_folder_finish, result)

    def _report_launch(self, finish, result):
        try:
            finish(result)
        except GLib.Error as error:
            if self.window:
                self.window.toast(f"Could not open it: {error.message}")


def main():
    if "--version" in sys.argv[1:]:
        print(f"{APP_NAME} {__version__}")
        return 0
    if "--remove-hotkey" in sys.argv[1:]:  # used by uninstall.sh
        hotkey.apply("")
        settings = config.load()
        if os.path.exists(config.config_path()):
            settings["hotkey"] = config.DEFAULT_HOTKEY
            config.save(settings)
        return 0
    GLib.set_prgname(APP_ID)
    GLib.set_application_name(APP_NAME)
    return Application().run(sys.argv)
