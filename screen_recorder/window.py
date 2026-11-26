"""The main window and the settings dialog."""

import os
import threading
import time

from gi.repository import Adw, Gdk, Gio, GLib, Gtk

from . import APP_NAME, audio, config, disk, encoders, hotkey
from .portal import ScreenCast
from .recorder import Recording, Settings, even, wayland_source, x11_source

IDLE, CHOOSING, STARTING, RECORDING, SAVING = (
    "idle", "choosing", "starting", "recording", "saving")


def is_wayland():
    session = os.environ.get("XDG_SESSION_TYPE", "").lower()
    if session in ("wayland", "x11"):
        return session == "wayland"
    return bool(os.environ.get("WAYLAND_DISPLAY"))


def monitors():
    """[(connector, label, (x, y, width, height))] in pixels."""
    result = []
    model = Gdk.Display.get_default().get_monitors()
    for index in range(model.get_n_items()):
        monitor = model.get_item(index)
        rect = monitor.get_geometry()
        scale = monitor.get_scale() if hasattr(monitor, "get_scale") \
            else monitor.get_scale_factor()
        box = tuple(round(v * scale) for v in (rect.x, rect.y, rect.width, rect.height))
        name = monitor.get_connector() or f"monitor-{index + 1}"
        result.append((name, f"{name}  ({box[2]}×{box[3]})", box))
    return result


def describe_stream(properties):
    """Name the monitor the portal chose, e.g. "HDMI-1 · 1366×768"."""
    position = tuple(properties.get("position") or ())
    size = tuple(properties.get("size") or ())
    model = Gdk.Display.get_default().get_monitors()
    matches = []
    for index in range(model.get_n_items()):
        monitor = model.get_item(index)
        rect = monitor.get_geometry()
        if (rect.x, rect.y) == position or (not position and (rect.width, rect.height) == size):
            matches.append(monitor)
    if len(matches) == 1:
        monitor = matches[0]
        rect = monitor.get_geometry()
        scale = monitor.get_scale() if hasattr(monitor, "get_scale") \
            else monitor.get_scale_factor()
        name = monitor.get_connector() or monitor.get_model() or "Screen"
        return f"{name} · {round(rect.width * scale)}×{round(rect.height * scale)}"
    if len(size) == 2:
        return f"Screen · {size[0]}×{size[1]}"
    return "The chosen screen"


def with_parent_handle(window, callback):
    """Call callback(handle) with the portal's name for `window`, or "".

    With it, the desktop's screen picker opens above this window.
    """
    surface = window.get_surface()
    minimized = surface is not None and hasattr(surface, "get_state") and \
        surface.get_state() & Gdk.ToplevelState.MINIMIZED
    if surface is None or not window.get_visible() or minimized:
        callback("")
        return
    kind = surface.__gtype__.name   # e.g. GdkWaylandToplevel, GdkX11Surface
    try:
        if kind.startswith("GdkWayland"):
            # Release the previous export, if any (one per picker request).
            old = getattr(window, "_exported_handle", None)
            if old is not None:
                if hasattr(surface, "drop_exported_handle"):  # GTK 4.12+
                    surface.drop_exported_handle(old)
                else:
                    surface.unexport_handle()
                window._exported_handle = None

            def exported(_toplevel, handle, *_data):
                window._exported_handle = handle
                callback(f"wayland:{handle}")
            if surface.export_handle(exported):
                return
        elif kind.startswith("GdkX11"):
            callback(f"x11:{surface.get_xid():x}")
            return
    except Exception as error:  # never block the picker over this
        print(f"No parent window for the screen picker: {error}")
    callback("")


def output_path(folder):
    stem = time.strftime("Recording_%Y-%m-%d_%H-%M-%S")
    path = os.path.join(folder, f"{stem}.mp4")
    number = 2
    while os.path.exists(path):
        path = os.path.join(folder, f"{stem}_{number}.mp4")
        number += 1
    return path


class DeviceRow:
    """A checkbox plus a device drop-down."""

    def __init__(self, title, missing_text, enabled, device, on_change):
        self.title = title
        self.missing_text = missing_text
        self.wanted = device
        self.ids = []
        self.on_change = on_change
        self._loading = True
        self.check = Gtk.CheckButton(active=enabled, valign=Gtk.Align.CENTER)
        self.row = Adw.ComboRow(title=title)
        self.row.add_prefix(self.check)
        self.row.set_activatable_widget(None)
        self.check.connect("toggled", self._changed)
        self.row.connect("notify::selected", self._changed)

    def set_devices(self, devices):
        self._loading = True
        self.ids = [d.id for d in devices]
        self.row.set_model(Gtk.StringList.new([d.label for d in devices]))
        if self.wanted in self.ids:
            self.row.set_selected(self.ids.index(self.wanted))
        self.check.set_sensitive(bool(devices))
        self.row.set_subtitle("" if devices else self.missing_text)
        self._loading = False

    @property
    def enabled(self):
        """The user's choice, kept even while no device is plugged in."""
        return self.check.get_active()

    @property
    def selected_id(self):
        index = self.row.get_selected()
        return self.ids[index] if 0 <= index < len(self.ids) else None

    @property
    def active_device(self):
        return self.selected_id if self.enabled else None

    def _changed(self, *_args):
        if self._loading:
            return
        if self.selected_id:
            # "Default" is stored as "" so it keeps following the system.
            self.wanted = self.selected_id
        self.on_change()


class Window(Adw.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app, title=APP_NAME,
                         default_width=480, default_height=720)
        self.set_size_request(460, 500)
        self.config = config.load()
        self.wayland = is_wayland()
        self.state = IDLE
        self.recording = None
        self.screencast = None
        self.encoder = None
        self.last_file = None
        self.close_when_saved = False
        self._start_when_ready = False
        self._ticker = None
        self._inhibit = 0
        self._ticks = 0

        self._build_ui()
        self.refresh_devices()
        self._set_state(IDLE)
        self.update_disk_info()
        self._idle_timer = GLib.timeout_add_seconds(10, self._idle_tick)
        self.connect("close-request", self._on_close)
        self.connect("notify::is-active", self._on_focus)

        self.missing = encoders.missing_packages(self.wayland)
        if self.missing:
            self._status("Some components are missing. Install them with:\n"
                         f"sudo apt install {' '.join(self.missing)}", error=True)
            self.start_button.set_sensitive(False)
        else:
            self._status("Looking for a video encoder…")
            threading.Thread(target=self._find_encoder, daemon=True).start()

    # -- layout --------------------------------------------------------------

    def _build_ui(self):
        header = Adw.HeaderBar()
        self.settings_button = Gtk.Button(icon_name="emblem-system-symbolic",
                                          tooltip_text="Settings")
        self.settings_button.connect("clicked", self._show_settings)
        header.pack_end(self.settings_button)

        self.banner = Adw.Banner()

        # screen
        sources = Adw.PreferencesGroup()
        self.monitor_names = []
        if self.wayland:
            self.screen_row = Adw.ActionRow(title="Screen", use_markup=False)
            self.screen_button = Gtk.Button(label="Choose…", valign=Gtk.Align.CENTER,
                                            tooltip_text="Pick the monitor to record")
            self.screen_button.connect("clicked", lambda *_: self.choose_screen())
            self.screen_row.add_suffix(self.screen_button)
            self._describe_screen_choice()
        else:
            self.screen_row = Adw.ComboRow(title="Screen")
            found = monitors()
            self.monitor_names = [m[0] for m in found]
            self.screen_row.set_model(Gtk.StringList.new([m[1] for m in found]))
            if self.config["monitor"] in self.monitor_names:
                self.screen_row.set_selected(
                    self.monitor_names.index(self.config["monitor"]))
            self.screen_row.connect("notify::selected", lambda *_: self._changed())
        sources.add(self.screen_row)

        # audio
        self.mic = DeviceRow("Microphone", "No microphone found",
                             self.config["mic_enabled"], self.config["mic_device"],
                             self._changed)
        self.system = DeviceRow("System audio", "No audio output found",
                                self.config["system_enabled"],
                                self.config["system_device"], self._changed)
        sources.add(self.mic.row)
        sources.add(self.system.row)

        # time, level and buttons
        self.timer_label = Gtk.Label(label="00:00:00")
        self.timer_label.add_css_class("timer")
        self.level = Gtk.LevelBar(min_value=0, max_value=1, margin_start=48,
                                  margin_end=48)
        self.status_label = Gtk.Label(wrap=True, justify=Gtk.Justification.CENTER,
                                      selectable=True)

        self.start_button = self._pill("Start", "suggested-action", self.start)
        self.pause_button = self._pill("Pause", None, self.toggle_pause)
        self.stop_button = self._pill("Stop", "destructive-action", self.stop)
        buttons = Gtk.Box(spacing=12, halign=Gtk.Align.CENTER)
        for button in (self.start_button, self.pause_button, self.stop_button):
            buttons.append(button)

        # saved file
        self.saved_row = Adw.ActionRow(title="Saved!", use_markup=False)
        saved_list = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE)
        saved_list.add_css_class("boxed-list")
        saved_list.append(self.saved_row)
        saved_buttons = Gtk.Box(spacing=12, halign=Gtk.Align.CENTER)
        for label, callback in (("Open folder", self._open_saved_folder),
                                ("Play", self._play_saved)):
            button = Gtk.Button(label=label)
            button.connect("clicked", callback)
            saved_buttons.append(button)
        self.saved_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8,
                                 visible=False)
        self.saved_box.append(saved_list)
        self.saved_box.append(saved_buttons)

        # destination
        destination = Adw.PreferencesGroup()
        self.folder_row = Adw.ActionRow(title="Save to", use_markup=False,
                                        subtitle=self.config["folder"])
        self.folder_button = Gtk.Button(label="Change folder",
                                        valign=Gtk.Align.CENTER)
        self.folder_button.connect("clicked", self._pick_folder)
        self.folder_row.add_suffix(self.folder_button)
        destination.add(self.folder_row)
        self.disk_label = Gtk.Label(wrap=True, justify=Gtk.Justification.CENTER)
        self.disk_label.add_css_class("dim-label")
        self.disk_label.add_css_class("caption")

        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14,
                          margin_top=14, margin_bottom=18,
                          margin_start=14, margin_end=14)
        for widget in (sources, self.timer_label, self.level, buttons,
                       self.status_label, self.saved_box, destination,
                       self.disk_label):
            content.append(widget)
        self.sources = sources

        scroller = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER,
                                      vexpand=True)
        scroller.set_child(Adw.Clamp(child=content, maximum_size=520))
        self.toasts = Adw.ToastOverlay(child=scroller)
        view = Adw.ToolbarView(content=self.toasts)
        view.add_top_bar(header)
        view.add_top_bar(self.banner)
        self.set_content(view)

    def _pill(self, label, style, action):
        button = Gtk.Button(label=label)
        button.add_css_class("pill")
        if style:
            button.add_css_class(style)
        button.connect("clicked", lambda *_: action())
        return button

    def _show_settings(self, _button):
        dialog = Adw.PreferencesDialog(content_width=440, content_height=520)
        page = Adw.PreferencesPage()
        video = Adw.PreferencesGroup(title="Video")

        rates = Adw.ComboRow(title="Frame rate", model=Gtk.StringList.new(
            [f"{r} fps" for r in config.FRAME_RATES]))
        rates.set_selected(config.FRAME_RATES.index(self.config["fps"]))
        quality = Adw.ComboRow(title="Quality", model=Gtk.StringList.new(
            [q.capitalize() for q in config.QUALITIES]))
        quality.set_selected(config.QUALITIES.index(self.config["quality"]))

        def video_changed(*_args):
            self.config["fps"] = config.FRAME_RATES[rates.get_selected()]
            self.config["quality"] = config.QUALITIES[quality.get_selected()]
            self._changed()

        rates.connect("notify::selected", video_changed)
        quality.connect("notify::selected", video_changed)
        video.add(rates)
        video.add(quality)
        if self.encoder:
            video.add(Adw.ActionRow(title="Encoder", subtitle=self.encoder.label))

        keys = Adw.PreferencesGroup(title="Global hotkey",
                                    description="Starts and stops recording from any app.")
        row = Adw.ActionRow(title="Shortcut")
        shown = Gtk.ShortcutLabel(disabled_text="Off", valign=Gtk.Align.CENTER,
                                  accelerator=self.config["hotkey"])
        row.add_suffix(shown)
        change = Gtk.Button(label="Change", valign=Gtk.Align.CENTER)
        clear = Gtk.Button(label="Turn off", valign=Gtk.Align.CENTER)
        keys.add(row)
        buttons = Gtk.Box(spacing=12, halign=Gtk.Align.CENTER, margin_top=12)
        buttons.append(change)
        buttons.append(clear)
        keys.add(buttons)
        if not hotkey.supported():
            keys.set_description("Global hotkeys need the GNOME desktop.")
            row.set_sensitive(False)
            buttons.set_sensitive(False)

        capture = Gtk.EventControllerKey(propagation_phase=Gtk.PropagationPhase.CAPTURE)
        waiting = [False]

        def finish(accelerator):
            waiting[0] = False
            change.set_label("Change")
            if accelerator is not None:
                self.set_hotkey(accelerator)
                shown.set_accelerator(accelerator)

        def key_pressed(_controller, keyval, _code, state):
            if not waiting[0]:
                return False
            mods = state & Gtk.accelerator_get_default_mod_mask()
            if keyval == Gdk.KEY_Escape and not mods:
                finish(None)
            elif Gtk.accelerator_valid(keyval, mods):
                function_key = Gdk.KEY_F1 <= keyval <= Gdk.KEY_F35
                # A plain letter would be taken away from every other app.
                if mods & ~Gdk.ModifierType.SHIFT_MASK or function_key:
                    other = hotkey.conflict(Gtk.accelerator_name(keyval, mods))
                    if other:
                        dialog.add_toast(Adw.Toast(title=f"Already used by {other}",
                                                   use_markup=False))
                    else:
                        finish(Gtk.accelerator_name(keyval, mods))
                else:
                    dialog.add_toast(Adw.Toast(title="Include Ctrl, Alt or Super"))
            return True

        def start_capture(_button):
            waiting[0] = True
            change.set_label("Press keys…")

        capture.connect("key-pressed", key_pressed)
        dialog.add_controller(capture)
        change.connect("clicked", start_capture)
        clear.connect("clicked", lambda *_: finish(""))

        page.add(video)
        page.add(keys)
        dialog.add(page)
        dialog.present(self)
        self.settings_dialog = dialog

    def set_hotkey(self, accelerator):
        self.config["hotkey"] = accelerator
        config.save(self.config)
        hotkey.apply(accelerator)

    # -- options -------------------------------------------------------------

    def refresh_devices(self):
        mics, outputs = audio.list_devices()
        self.mic.set_devices(mics)
        self.system.set_devices(outputs)

    def _on_focus(self, *_args):
        if self.is_active() and self.state == IDLE:
            self.refresh_devices()  # picks up newly plugged-in devices
            self.update_disk_info()

    def _store_options(self):
        self.config.update(
            mic_enabled=self.mic.enabled, mic_device=self.mic.wanted,
            system_enabled=self.system.enabled, system_device=self.system.wanted)
        if self.monitor_names:
            index = self.screen_row.get_selected()
            if index < len(self.monitor_names):
                self.config["monitor"] = self.monitor_names[index]

    def _changed(self):
        self._store_options()
        config.save(self.config)
        self.update_disk_info()

    def _describe_screen_choice(self):
        if self.config["restore_token"]:
            subtitle = self.config["screen_label"] or "The screen you chose last time"
        elif self.config["screen_label"]:
            subtitle = f"{self.config['screen_label']} (asked again at Start)"
        else:
            subtitle = "Not chosen yet: press Choose…, or you will be asked at Start"
        self.screen_row.set_subtitle(subtitle)

    def _remember_screen(self, restore_token, properties):
        self.config["restore_token"] = restore_token
        self.config["screen_label"] = describe_stream(properties)
        config.save(self.config)
        self._describe_screen_choice()

    def choose_screen(self):
        """Wayland: open the desktop's picker now and remember the choice."""
        if self.state != IDLE:
            return
        self._set_state(CHOOSING)
        self._status("Pick the screen in the dialog, then press Share.")
        self.screencast = ScreenCast(on_closed=self._screen_share_ended)
        # No restore token: always show the picker.
        with_parent_handle(self, lambda parent: self.screencast and self.screencast.open(
            "", self._screen_chosen, self._screen_failed, parent))

    def _screen_chosen(self, _fd, _node_id, restore_token, properties):
        self._close_screencast()  # only the choice is needed now
        self._remember_screen(restore_token, properties)
        self._set_state(IDLE)
        self._status(f"Will record {self.config['screen_label']}.")

    def _pick_folder(self, _button):
        dialog = Gtk.FileDialog(title="Choose where to save recordings")
        if os.path.isdir(self.config["folder"]):
            dialog.set_initial_folder(Gio.File.new_for_path(self.config["folder"]))

        def done(dialog, result):
            try:
                chosen = dialog.select_folder_finish(result)
            except GLib.Error:
                return
            if chosen and chosen.get_path():
                self.set_folder(chosen.get_path())

        dialog.select_folder(self, None, done)

    def set_folder(self, folder):
        self.config["folder"] = folder
        self.folder_row.set_subtitle(folder)
        self._changed()

    # -- disk space ----------------------------------------------------------

    def _frame_size(self):
        found = monitors()
        if not self.wayland and found:
            index = min(self.screen_row.get_selected(), len(found) - 1)
            return found[index][2][2:]
        if self.config["last_size"]:
            return tuple(self.config["last_size"])
        if found:
            return max((m[2][2:] for m in found), key=lambda s: s[0] * s[1])
        return (1920, 1080)

    def _estimate(self):
        width, height = self._frame_size()
        return disk.estimate_per_hour(
            width, height, self.config["fps"], self.config["quality"],
            audio=bool(self.mic.active_device or self.system.active_device))

    def update_disk_info(self):
        try:
            free = disk.free_bytes(self.config["folder"])
        except OSError:
            self.disk_label.set_label("The save folder is not available.")
            return
        per_hour = (self.recording.bytes_per_hour() if self.recording
                    else self._estimate())
        hours = disk.hours_left(free, per_hour)
        remaining = "over 99 h" if hours > 99 else f"about {hours:.1f} h"
        text = (f"Free {disk.format_size(free)} · about "
                f"{disk.format_size(per_hour)} per hour · room for {remaining}")
        if self.recording:
            text = f"File {disk.format_size(self.recording.bytes_written())} · {text}"
        self.disk_label.set_label(text)
        if hours < disk.SOAK_HOURS:
            self.banner.set_title(
                f"Not enough free space for {disk.SOAK_HOURS} hours "
                f"(room for about {hours:.1f} h)")
        self.banner.set_revealed(hours < disk.SOAK_HOURS)

    def _idle_tick(self):
        if self.state == IDLE:
            self.update_disk_info()
        return True

    # -- recording -----------------------------------------------------------

    def _find_encoder(self):
        encoder = encoders.pick_encoder()
        GLib.idle_add(self._encoder_found, encoder)

    def _encoder_found(self, encoder):
        self.encoder = encoder
        if encoder is None:
            self._status("No working H.264 encoder. Install "
                         "gstreamer1.0-plugins-ugly.", error=True)
            return False
        if self.state == IDLE:
            self._status(f"Ready · {encoder.label}")
        self._set_state(self.state)
        if self._start_when_ready:
            self._start_when_ready = False
            self.start()
        return False

    def toggle(self):
        """Start or stop: used by the global hotkey."""
        if self.state == IDLE:
            if self.encoder is None and not self.missing:
                self._start_when_ready = True
            else:
                self.start()
        elif self.state in (STARTING, RECORDING):
            self.stop()
        else:  # choosing a screen or saving: let that finish
            self.present()

    def start(self):
        if self.state != IDLE or self.encoder is None:
            return
        self.refresh_devices()
        self._store_options()
        for row in (self.mic, self.system):
            if row.enabled and row.selected_id is None:
                self._fail(f"{row.missing_text}. Connect one, or untick "
                           f"“{row.title}” to record without it.")
                return
        folder = self.config["folder"]
        try:
            os.makedirs(folder, exist_ok=True)
        except OSError as error:
            self._fail(f"Cannot use that folder: {error.strerror}")
            return
        if not os.access(folder, os.W_OK | os.X_OK):
            self._fail("You do not have permission to write to that folder.")
            return
        free = disk.free_bytes(folder)
        needed = disk.stop_threshold(self._estimate())
        if free < needed:
            self._fail(f"Not enough free space: {disk.format_size(free)} free, at "
                       f"least {disk.format_size(needed)} is needed.")
            return
        config.save(self.config)

        self.saved_box.set_visible(False)
        self.timer_label.set_label("00:00:00")
        self._set_state(STARTING)

        if self.wayland:
            self._status("Opening the screen…" if self.config["restore_token"] else
                         "Pick the screen in the dialog, then press Share.")
            self.screencast = ScreenCast(on_closed=self._screen_share_ended)
            with_parent_handle(self, lambda parent: self.screencast and self.screencast.open(
                self.config["restore_token"], self._screen_ready, self._screen_failed,
                parent))
        else:
            found = monitors()
            if not found:
                self._cancel("No monitor was found.", error=True)
                return
            index = min(self.screen_row.get_selected(), len(found) - 1)
            x, y, width, height = found[index][2]
            self._begin(x11_source(x, y, even(width), even(height), self.config["fps"]))

    def _screen_ready(self, fd, node_id, restore_token, properties):
        self._remember_screen(restore_token, properties)
        self._begin(wayland_source(fd, node_id))

    def _screen_failed(self, message):
        if message is None:
            self._cancel("Screen selection cancelled.")
        else:
            self._cancel(message, error=True)

    def _begin(self, source):
        settings = Settings(
            output=output_path(self.config["folder"]), source=source,
            encoder=self.encoder, fps=self.config["fps"],
            quality=self.config["quality"], mic=self.mic.active_device,
            system=self.system.active_device)
        try:
            self.recording = Recording(settings, self._finished, self._show_level)
        except (GLib.Error, ValueError) as error:
            self._cancel(f"Could not start: {getattr(error, 'message', error)}",
                         error=True)
            return
        app = self.get_application()
        app.hold()
        # Keep the screen from locking or the computer sleeping mid-recording.
        self._inhibit = app.inhibit(
            self, Gtk.ApplicationInhibitFlags.IDLE
            | Gtk.ApplicationInhibitFlags.SUSPEND
            | Gtk.ApplicationInhibitFlags.LOGOUT, "Recording the screen")
        self._set_state(RECORDING)
        self._status(self._recording_text())
        self.recording.start()
        if self.recording and self._ticker is None:
            self._ticker = GLib.timeout_add(250, self._tick)

    def toggle_pause(self):
        if self.state != RECORDING or self.recording is None:
            return
        self.recording.set_paused(not self.recording.paused)
        paused = self.recording.paused
        self.pause_button.set_label("Resume" if paused else "Pause")
        self._status("Paused" if paused else self._recording_text())

    def _recording_text(self):
        if self.wayland:
            return f"● Recording {self.config['screen_label']}"
        found = monitors()
        index = self.screen_row.get_selected()
        return f"● Recording {found[index][1]}" if index < len(found) else "● Recording"

    def stop(self):
        if self.state in (CHOOSING, STARTING):
            self._cancel("Cancelled.")
        elif self.state == RECORDING and self.recording is not None:
            self._set_state(SAVING)
            self._status("Saving the file…")
            self.recording.stop()

    def _tick(self):
        if self.recording is None:
            self._ticker = None
            return False
        seconds = int(self.recording.elapsed())
        self.timer_label.set_label(
            f"{seconds // 3600:02}:{seconds // 60 % 60:02}:{seconds % 60:02}")
        self._ticks += 1
        if self._ticks % 20 == 0:  # every 5 seconds
            self.update_disk_info()
        return True

    def _show_level(self, decibels):
        if self.recording is not None and not self.recording.paused:
            self.level.set_value(min(1.0, max(0.0, (decibels + 60) / 60)))
        else:
            self.level.set_value(0)

    def _screen_share_ended(self):
        if self.state == RECORDING:
            self.stop()
        elif self.state in (CHOOSING, STARTING):
            self._cancel("Screen sharing was stopped.")

    def _finished(self, path, error, notice):
        if self.recording is not None and self.recording.size:
            self.config["last_size"] = list(self.recording.size)
            config.save(self.config)
        self.recording = None
        self._close_screencast()
        app = self.get_application()
        if self._inhibit:
            app.uninhibit(self._inhibit)
            self._inhibit = 0
        self._set_state(IDLE)

        if error:
            kept = f"\nThe recording up to that point was saved." if path else ""
            self._status(f"{error}{kept}", error=True)
        else:
            self._status(notice or "")
        if path:
            self.last_file = path
            self.saved_row.set_title("Saved!" if not error else "Partial recording saved")
            self.saved_row.set_subtitle(os.path.basename(path))
            self.saved_box.set_visible(True)
        app.notify_finished(path, error, notice)
        self.update_disk_info()
        app.release()
        if self.close_when_saved:
            self.close_when_saved = False
            self.close()  # the application exits when no window is left

    # -- state ---------------------------------------------------------------

    def _set_state(self, state):
        self.state = state
        idle = state == IDLE
        for widget in (self.sources, self.folder_button, self.settings_button):
            widget.set_sensitive(idle)
        self.start_button.set_sensitive(idle and self.encoder is not None)
        self.pause_button.set_sensitive(state == RECORDING)
        self.stop_button.set_sensitive(state in (CHOOSING, STARTING, RECORDING))
        self.pause_button.set_label("Pause")
        self.level.set_value(0)

    def _status(self, text, error=False):
        self.status_label.set_label(text)
        self.status_label.set_visible(bool(text))
        if error:
            self.status_label.add_css_class("error")
        else:
            self.status_label.remove_css_class("error")

    def _fail(self, message):
        self._status(message, error=True)
        self.present()

    def _cancel(self, message, error=False):
        self._close_screencast()
        self._set_state(IDLE)
        self._status(message, error=error)
        if error:
            self.present()

    def _close_screencast(self):
        if self.screencast is not None:
            self.screencast.close()
            self.screencast = None

    def shutdown(self):
        """Close the window, finishing any recording first."""
        self.close_when_saved = True
        if self.recording is not None:
            self.stop()
        else:
            self.close_when_saved = False
            self.close()

    def _on_close(self, _window):
        if self.recording is not None:
            self.close_when_saved = True
            self.stop()
            return True  # closes once the file is saved
        if self.state != IDLE:
            self._cancel("Cancelled.")
        self._store_options()
        config.save(self.config)
        GLib.source_remove(self._idle_timer)
        self.get_application().window_closed()
        return False

    # -- saved file ----------------------------------------------------------

    def _open_saved_folder(self, _button):
        self.get_application().open_folder(self.last_file)

    def _play_saved(self, _button):
        self.get_application().play(self.last_file)

    def toast(self, text):
        self.toasts.add_toast(Adw.Toast(title=text, use_markup=False))
