#!/usr/bin/python3
"""Drive the real window: start, pause, resume, stop, settings, close.

    /usr/bin/python3 tests/ui_test.py [screenshot-folder]

Runs with temporary settings and in-memory desktop settings, so your own
configuration and keyboard shortcuts are not changed. The screen picker is
replaced by a test picture. A window opens for about half a minute.
"""

import os
import sys
import tempfile

SHOTS = os.path.abspath(sys.argv[1]) if len(sys.argv) > 1 else None
SANDBOX = tempfile.mkdtemp(prefix="recorder-ui-")
os.environ["XDG_CONFIG_HOME"] = os.path.join(SANDBOX, "config")
os.environ["GSETTINGS_BACKEND"] = "memory"

import common  # noqa: E402,F401  (adds the project to sys.path)
from gi.repository import GLib, Graphene, Gtk  # noqa: E402

from screen_recorder import config, hotkey, window  # noqa: E402
from screen_recorder.app import Application  # noqa: E402

failures = []
opened = []   # (restore token, parent window) for each picker request


class FakeScreenCast:
    def __init__(self, on_closed=None):
        pass

    def open(self, token, on_ready, on_error, parent=""):
        opened.append((token, parent))
        GLib.idle_add(lambda: on_ready(0, 0, "token-2",
                                       {"position": (0, 0), "size": (1920, 1200)}) and False)

    def close(self):
        pass


window.ScreenCast = FakeScreenCast
window.wayland_source = lambda fd, node: common.test_source()
window.x11_source = lambda x, y, w, h, fps: common.test_source(fps=fps)


def check(name, condition, detail=""):
    print(f"{'ok  ' if condition else 'FAIL'} {name} {detail}", flush=True)
    if not condition:
        failures.append(name)


def screenshot(widget, name):
    if not SHOTS:
        return
    width, height = widget.get_width(), widget.get_height()
    snapshot = Gtk.Snapshot()
    Gtk.WidgetPaintable.new(widget).snapshot(snapshot, width, height)
    node = snapshot.to_node()
    if node is None:
        print(f"     (no screenshot of {name}: window not drawn)")
        return
    os.makedirs(SHOTS, exist_ok=True)
    widget.get_renderer().render_texture(
        node, Graphene.Rect().init(0, 0, width, height)).save_to_png(
            os.path.join(SHOTS, f"{name}.png"))


def script(app):
    win = app.window
    folder = os.path.join(SANDBOX, "recordings")
    win.set_folder(folder)
    yield 2500
    check("encoder found", win.encoder is not None)
    check("idle buttons", win.start_button.get_sensitive()
          and not win.pause_button.get_sensitive() and not win.stop_button.get_sensitive())
    check("disk info", "per hour" in win.disk_label.get_label(), win.disk_label.get_label())
    screenshot(win, "1_idle")

    # Choosing the screen opens the picker at once and shows the choice.
    if win.wayland:
        win.screen_button.emit("clicked")
        yield 1500
        check("choose screen", win.state == window.IDLE and opened
              and opened[-1][0] == "" and opened[-1][1].startswith("wayland:")
              and config.load()["restore_token"] == "token-2"
              and "×" in win.screen_row.get_subtitle(),
              f"{opened} / {win.screen_row.get_subtitle()}")
        screenshot(win, "1b_screen_chosen")

    win.settings_button.emit("clicked")
    yield 1000
    screenshot(win, "2_settings")
    win.settings_dialog.close()
    win.set_hotkey("<Super>F9")
    item = hotkey.Gio.Settings.new_with_path(hotkey.ITEM_SCHEMA, hotkey.PATH)
    check("hotkey registered", item.get_string("binding") == "<Super>F9"
          and item.get_string("command").endswith("--toggle"), item.get_string("command"))
    check("hotkey saved", config.load()["hotkey"] == "<Super>F9")
    yield 500

    win.start_button.emit("clicked")
    yield 4000
    check("recording", win.state == window.RECORDING and win.timer_label.get_label() >= "00:00:02",
          win.timer_label.get_label())
    if win.wayland:
        check("saved choice reused", opened[-1][0] == "token-2", str(opened[-1]))
    screenshot(win, "3_recording")
    win.pause_button.emit("clicked")
    yield 500
    frozen = win.timer_label.get_label()
    yield 2000
    check("paused", win.pause_button.get_label() == "Resume"
          and win.timer_label.get_label() == frozen, frozen)
    win.pause_button.emit("clicked")
    yield 2000
    win.stop_button.emit("clicked")
    yield 3000
    check("saved", win.state == window.IDLE and win.saved_box.get_visible()
          and win.last_file and os.path.getsize(win.last_file) > 0,
          win.saved_row.get_subtitle())
    name = os.path.basename(win.last_file or "")
    check("file name", name.startswith("Recording_") and name.endswith(".mp4"), name)
    streams, duration = common.probe(win.last_file)
    check("file content", {"video", "audio"} <= set(streams) and 5 < duration < 7,
          f"{duration:.2f}s {sorted(streams)}")
    screenshot(win, "4_saved")

    # The hotkey path: toggle starts, toggle stops.
    app.window.toggle()
    yield 3000
    check("toggle starts", win.state == window.RECORDING)
    app.window.toggle()
    yield 3000
    check("toggle stops", win.state == window.IDLE and len(os.listdir(folder)) == 2)

    # Unticked boxes record video only.
    win.mic.check.set_active(False)
    win.system.check.set_active(False)
    win.start_button.emit("clicked")
    yield 3000
    # Closing during a recording must still finish the file.
    win.close()
    yield 4000
    files = sorted(os.listdir(folder))
    check("close while recording", len(files) == 3 and app.window is None, str(files))
    streams, _ = common.probe(os.path.join(folder, files[-1]))
    check("video-only file", set(streams) == {"video"}, str(sorted(streams)))


def main():
    app = Application("io.github.local.ScreenRecorderUITest")
    finished = []

    def begin():
        steps = script(app)

        def step():
            try:
                GLib.timeout_add(next(steps), step)
            except StopIteration:
                finished.append(True)
                app.quit()
            except Exception as error:  # report and leave
                import traceback
                traceback.print_exc()
                failures.append(str(error))
                app.quit()
            return False

        step()
        return False

    app.hold()
    GLib.timeout_add(1000, begin)
    app.run([sys.argv[0]])
    if not finished:
        failures.append("script did not finish")
    print(f"\nfiles in {SANDBOX}")
    print("UI TEST PASSED" if not failures else f"UI TEST FAILED: {failures}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
