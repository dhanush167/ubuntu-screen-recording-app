"""Screen capture permission on Wayland through xdg-desktop-portal."""

import itertools
import os

from gi.repository import Gio, GLib

BUS_NAME = "org.freedesktop.portal.Desktop"
OBJECT_PATH = "/org/freedesktop/portal/desktop"
SCREENCAST = "org.freedesktop.portal.ScreenCast"

SOURCE_MONITOR = 1
CURSOR_EMBEDDED = 2
PERSIST_UNTIL_REVOKED = 2

_tokens = itertools.count(1)


class ScreenCast:
    """One screen-sharing session.

    open() shows the desktop's monitor picker (skipped when a saved
    restore_token is still valid), then calls
    on_ready(fd, node_id, restore_token, stream_properties) or on_error(message).
    on_error(None) means the user cancelled. on_closed() is called if the
    desktop ends the session, for example from the top-bar indicator.

    parent_window is "wayland:<handle>", "x11:<id>" or "": it keeps the picker
    above the app's window.
    """

    def __init__(self, on_closed=None):
        self.bus = None
        self.on_closed = on_closed
        self.session = None
        self.fd = None
        self._closed_sub = None
        self._pending = set()

    def open(self, restore_token, on_ready, on_error, parent_window=""):
        self._on_ready = on_ready
        self._on_error = on_error
        self._restore_token = restore_token
        self._parent = parent_window
        try:
            self.bus = Gio.bus_get_sync(Gio.BusType.SESSION)
            self._version = self.bus.call_sync(
                BUS_NAME, OBJECT_PATH, "org.freedesktop.DBus.Properties", "Get",
                GLib.Variant("(ss)", (SCREENCAST, "version")), GLib.VariantType("(v)"),
                Gio.DBusCallFlags.NONE, 5000, None).unpack()[0]
        except GLib.Error as error:
            self._fail("Screen capture is not available. Is xdg-desktop-portal-gnome "
                       f"installed and running? ({error.message})")
            return
        self._request(
            "CreateSession", "(a{sv})", [],
            {"session_handle_token": GLib.Variant("s", self._token("session"))},
            self._session_created,
        )

    def close(self):
        if self.bus is None:
            return
        for sub in self._pending:
            self.bus.signal_unsubscribe(sub)
        self._pending.clear()
        if self._closed_sub is not None:
            self.bus.signal_unsubscribe(self._closed_sub)
            self._closed_sub = None
        if self.session:
            self.bus.call(BUS_NAME, self.session, "org.freedesktop.portal.Session",
                          "Close", None, None, Gio.DBusCallFlags.NONE, -1, None, None)
            self.session = None
        if self.fd is not None:
            try:
                os.close(self.fd)
            except OSError:
                pass
            self.fd = None

    # -- steps ---------------------------------------------------------------

    def _session_created(self, results):
        self.session = results["session_handle"]
        self._closed_sub = self.bus.signal_subscribe(
            BUS_NAME, "org.freedesktop.portal.Session", "Closed", self.session,
            None, Gio.DBusSignalFlags.NONE, self._session_closed)
        options = {
            "types": GLib.Variant("u", SOURCE_MONITOR),
            "multiple": GLib.Variant("b", False),
            "cursor_mode": GLib.Variant("u", CURSOR_EMBEDDED),
        }
        if self._version >= 4:
            options["persist_mode"] = GLib.Variant("u", PERSIST_UNTIL_REVOKED)
            if self._restore_token:
                options["restore_token"] = GLib.Variant("s", self._restore_token)
        self._request("SelectSources", "(oa{sv})", [self.session], options,
                      self._sources_selected)

    def _sources_selected(self, _results):
        self._request("Start", "(osa{sv})", [self.session, self._parent], {},
                      self._started)

    def _started(self, results):
        streams = results.get("streams")
        if not streams:
            self._fail("No screen was selected.")
            return
        node_id, properties = streams[0]
        try:
            reply, fd_list = self.bus.call_with_unix_fd_list_sync(
                BUS_NAME, OBJECT_PATH, SCREENCAST, "OpenPipeWireRemote",
                GLib.Variant("(oa{sv})", (self.session, {})),
                GLib.VariantType("(h)"), Gio.DBusCallFlags.NONE, -1, None, None)
            self.fd = fd_list.get(reply.unpack()[0])
        except GLib.Error as error:
            self._fail(f"Could not open the screen stream: {error.message}")
            return
        # A restore token works once; the portal hands out the next one here.
        self._on_ready(self.fd, node_id, results.get("restore_token", ""),
                       dict(properties))

    # -- helpers -------------------------------------------------------------

    def _token(self, prefix):
        return f"{prefix}_{os.getpid()}_{next(_tokens)}"

    def _request(self, method, signature, args, options, then):
        token = self._token("request")
        sender = self.bus.get_unique_name()[1:].replace(".", "_")
        path = f"{OBJECT_PATH}/request/{sender}/{token}"

        def on_response(_bus, _sender, _path, _iface, _signal, params):
            self.bus.signal_unsubscribe(sub)
            self._pending.discard(sub)
            code, results = params.unpack()
            if code == 0:
                then(results)
            elif code == 1:
                self._fail(None)
            else:
                self._fail("Permission to capture the screen was denied.")

        sub = self.bus.signal_subscribe(
            BUS_NAME, "org.freedesktop.portal.Request", "Response", path, None,
            Gio.DBusSignalFlags.NONE, on_response)
        self._pending.add(sub)

        options = dict(options, handle_token=GLib.Variant("s", token))

        def on_call_done(bus, result):
            try:
                bus.call_finish(result)
            except GLib.Error as error:
                self._fail(f"Screen capture is not available: {error.message}")

        self.bus.call(
            BUS_NAME, OBJECT_PATH, SCREENCAST, method,
            GLib.Variant(signature, (*args, options)), None,
            Gio.DBusCallFlags.NONE, -1, None, on_call_done)

    def _fail(self, message):
        callback = self._on_error
        self.close()
        callback(message)

    def _session_closed(self, *_args):
        self.session = None
        if self.on_closed:
            self.on_closed()
