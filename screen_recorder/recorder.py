"""The recording engine: one GStreamer pipeline per recording."""

import os
from dataclasses import dataclass

from gi.repository import GLib, Gst

from . import disk
from .pacer import FramePacer

STOP_TIMEOUT_SECONDS = 20
ERROR_STOP_TIMEOUT_SECONDS = 5
START_TIMEOUT_SECONDS = 15
AUDIO_BLOCK_NS = 10 * Gst.MSECOND   # audiomixer's output buffer length
DISK_CHECK_SECONDS = 5
MEASURE_AFTER_SECONDS = 60


def quote(value):
    return '"' + str(value).replace("\\", "\\\\").replace('"', '\\"') + '"'


def even(value):
    return max(2, int(value) // 2 * 2)


def wayland_source(fd, node_id):
    """Screen frames from the portal's PipeWire stream."""
    # Frames arrive only when the screen changes; FramePacer repeats them.
    # Do not add keepalive-time: see pacer.py.
    return (f"pipewiresrc name=screen fd={int(fd)} path={int(node_id)} "
            "do-timestamp=true always-copy=true")


def x11_source(x, y, width, height, fps):
    """One monitor of an X11 desktop, in pixels."""
    return (f"ximagesrc name=screen use-damage=false show-pointer=true "
            f"startx={int(x)} starty={int(y)} "
            f"endx={int(x + width - 1)} endy={int(y + height - 1)} ! "
            f"video/x-raw,framerate={fps}/1")


@dataclass
class Settings:
    output: str                 # .mp4 path that does not exist yet
    source: str                 # gst-launch fragment producing screen frames
    encoder: object             # encoders.Encoder
    fps: int = 30
    quality: str = "medium"
    mic: str = None             # PulseAudio source name, None = off
    system: str = None          # monitor source name, None = off
    min_free: int = None        # override the low-disk limit (for tests)


def build_description(settings):
    fps = settings.fps
    encoder = settings.encoder
    audio = [(name, device) for name, device in
             (("mic", settings.mic), ("system", settings.system)) if device]

    # Fragmented MP4: an index is written every second, so the file stays
    # playable even if the app or the computer dies mid-recording.
    chains = [f"mp4mux name=mux fragment-duration=1000 ! "
              f"filesink location={quote(settings.output)}"]

    chains.append(
        f"{settings.source} ! "
        "queue name=vin max-size-buffers=3 max-size-bytes=0 max-size-time=0 "
        "leaky=downstream ! "
        "videoconvert n-threads=4 ! videoscale add-borders=true ! "
        f"capsfilter name=framesize caps=video/x-raw,format={encoder.raw_format},"
        "pixel-aspect-ratio=1/1 ! "
        "appsink name=grab emit-signals=true sync=false async=false "
        "max-buffers=1 drop=true")

    # The pacer repeats the newest screen frame at a constant rate.
    chains.append(
        "appsrc name=feed is-live=true format=time ! "
        # If the encoder cannot keep up, drop frames rather than fall behind.
        "queue name=vpause max-size-buffers=8 max-size-bytes=0 max-size-time=0 "
        "leaky=downstream ! "
        # Rewrites timestamps into one continuous timeline after a pause.
        "identity single-segment=true ! "
        f"{encoder.description(settings.quality, fps)} ! "
        "queue max-size-buffers=0 max-size-bytes=0 max-size-time=10000000000 ! mux.")

    if audio:
        caps = "audio/x-raw,rate=48000,channels=2"
        chains.append(
            f"audiomixer name=mix latency=200000000 ! {caps} ! "
            "level name=level interval=100000000 ! "
            "queue name=apause max-size-buffers=0 max-size-bytes=0 "
            "max-size-time=10000000000 ! "
            "identity single-segment=true ! audioconvert ! "
            f"avenc_aac bitrate={disk.AUDIO_BITRATE[settings.quality]} ! aacparse ! "
            "queue max-size-buffers=0 max-size-bytes=0 max-size-time=10000000000 ! mux.")
        for name, device in audio:
            # slave-method=skew (the default) keeps each sound card in step
            # with the pipeline clock over many hours.
            chains.append(
                f"pulsesrc name={name} device={quote(device)} "
                "client-name=\"Screen Recorder\" provide-clock=false "
                "slave-method=skew buffer-time=500000 ! "
                "queue max-size-buffers=0 max-size-bytes=0 max-size-time=10000000000 ! "
                f"audioconvert ! audioresample ! {caps} ! mix.")
    return " ".join(chains)


def describe_error(source_name, error, debug):
    """Turn a GStreamer error into a message a user can act on."""
    text = f"{error.message} {debug or ''}".lower()
    if "no space left" in text or error.matches(
            Gst.ResourceError.quark(), Gst.ResourceError.NO_SPACE_LEFT):
        return "The disk is full."
    if "permission denied" in text or "not authorized" in text:
        return f"Permission denied: {error.message}"
    if source_name == "mic":
        return ("The microphone stopped working or could not be opened. "
                f"Check that it is connected. ({error.message})")
    if source_name == "system":
        return ("System audio could not be recorded. Check the output device. "
                f"({error.message})")
    if source_name == "screen":
        return f"Screen capture stopped working. ({error.message})"
    return error.message


class Recording:
    """A single recording.

    on_finished(path, error, notice) is called exactly once from the main loop.
    path is None if no usable file exists. notice explains an automatic stop.
    on_level(decibels) reports the audio level about ten times a second.
    """

    def __init__(self, settings, on_finished, on_level=None):
        if os.path.exists(settings.output):
            raise ValueError("The output file already exists.")
        self.settings = settings
        self.on_finished = on_finished
        self.on_level = on_level
        self.size = None            # (width, height) once known

        self._paused = False
        self._stopping = False
        self._done = False
        self._error = None
        self._notice = None
        self._got_video = False
        self._pauses = []           # [start, end] in pipeline running time (ns)
        self._pause_started = 0
        self._paused_total = 0
        self._started_at = None
        self._timers = {}

        self.pipeline = Gst.parse_launch(build_description(settings))
        # One monotonic clock for everything keeps audio and video in step.
        self.pipeline.use_clock(Gst.SystemClock.obtain())
        self._pacer = FramePacer(self.pipeline, settings.fps)

        self._element_pad("vin", "sink").add_probe(
            Gst.PadProbeType.EVENT_DOWNSTREAM, self._fix_frame_size)
        self._element_pad("vpause", "sink").add_probe(
            Gst.PadProbeType.BUFFER, self._first_frame)
        for name in ("vpause", "apause"):
            element = self.pipeline.get_by_name(name)
            if element is not None:
                element.get_static_pad("src").add_probe(
                    Gst.PadProbeType.BUFFER, self._gate,
                    element.get_static_pad("sink"))

        self._bus = self.pipeline.get_bus()
        self._bus.add_signal_watch()
        self._bus.connect("message", self._on_message)

    def _element_pad(self, element, pad):
        return self.pipeline.get_by_name(element).get_static_pad(pad)

    # -- control ------------------------------------------------------------

    def start(self):
        if self.pipeline.set_state(Gst.State.PLAYING) == Gst.StateChangeReturn.FAILURE:
            message = self._bus.pop_filtered(Gst.MessageType.ERROR)
            if message:
                error, debug = message.parse_error()
                self._error = describe_error(message.src.get_name(), error, debug)
            else:
                self._error = "The recording could not be started."
            self._finish()
            return
        self._started_at = GLib.get_monotonic_time()
        self._timers["start"] = GLib.timeout_add_seconds(
            START_TIMEOUT_SECONDS, self._check_started)
        self._timers["disk"] = GLib.timeout_add_seconds(
            DISK_CHECK_SECONDS, self._check_disk)

    @property
    def paused(self):
        return self._paused

    @property
    def stopping(self):
        return self._stopping or self._done

    def elapsed(self):
        """Seconds of recorded material (pauses excluded)."""
        if self._started_at is None:
            return 0.0
        now = self._pause_started if self._paused else GLib.get_monotonic_time()
        return max(0.0, (now - self._started_at - self._paused_total) / 1e6)

    def bytes_written(self):
        try:
            return os.path.getsize(self.settings.output)
        except OSError:
            return 0

    def bytes_per_hour(self):
        """Measured growth rate once there is enough data, else an estimate."""
        seconds = self.elapsed()
        if seconds >= MEASURE_AFTER_SECONDS:
            return int(self.bytes_written() * 3600 / seconds)
        width, height = self.size or (1920, 1080)
        return disk.estimate_per_hour(
            width, height, self.settings.fps, self.settings.quality,
            audio=bool(self.settings.mic or self.settings.system))

    def set_paused(self, paused):
        if paused == self._paused or self.stopping or self._started_at is None:
            return
        clock = self.pipeline.get_clock()
        if clock is None:  # still starting up
            return
        # Cutting on whole audio blocks keeps the audio exactly continuous.
        running_time = clock.get_time() - self.pipeline.get_base_time()
        running_time -= running_time % AUDIO_BLOCK_NS
        now = GLib.get_monotonic_time()
        if paused:
            self._pause_started = now
            self._pauses.append([running_time, None])
        else:
            self._paused_total += now - self._pause_started
            self._pauses[-1][1] = running_time
        self._paused = paused

    def stop(self, notice=None):
        """Finish the file. on_finished is called once it is complete."""
        if self.stopping:
            return
        self._notice = notice
        self._send_eos(STOP_TIMEOUT_SECONDS)

    # -- pipeline callbacks (streaming threads) -----------------------------

    def _fix_frame_size(self, _pad, info):
        # Lock the output to the first size seen (rounded to even numbers, as
        # H.264 requires). Later size changes are scaled to fit.
        event = info.get_event()
        if event.type != Gst.EventType.CAPS or self.size is not None:
            return Gst.PadProbeReturn.OK
        structure = event.parse_caps().get_structure(0)
        ok_w, width = structure.get_int("width")
        ok_h, height = structure.get_int("height")
        if ok_w and ok_h:
            self.size = (even(width), even(height))
            self.pipeline.get_by_name("framesize").set_property(
                "caps", Gst.Caps.from_string(
                    f"video/x-raw,format={self.settings.encoder.raw_format},"
                    f"width={self.size[0]},height={self.size[1]},pixel-aspect-ratio=1/1"))
        return Gst.PadProbeReturn.OK

    def _first_frame(self, _pad, _info):
        self._got_video = True
        return Gst.PadProbeReturn.REMOVE

    def _gate(self, pad, info, sink_pad):
        # Pausing drops raw buffers and shifts later ones back in time, so the
        # file has no gap. Each buffer is judged by its own timestamp, because
        # video and audio do not reach this point at the same moment.
        pts = info.get_buffer().pts
        segment = sink_pad.get_sticky_event(Gst.EventType.SEGMENT, 0)
        if pts == Gst.CLOCK_TIME_NONE or segment is None:
            return Gst.PadProbeReturn.OK
        time = segment.parse_segment().to_running_time(Gst.Format.TIME, pts)
        skipped = 0
        for start, end in tuple(self._pauses):
            if end is None:
                if time >= start:
                    return Gst.PadProbeReturn.DROP
            elif time >= end:
                skipped += end - start
            elif time >= start:
                return Gst.PadProbeReturn.DROP
        if pad.get_offset() != -skipped:
            pad.set_offset(-skipped)  # applies to this buffer onwards
        return Gst.PadProbeReturn.OK

    # -- main loop ----------------------------------------------------------

    def _on_message(self, _bus, message):
        if self._done:
            return
        if message.type == Gst.MessageType.EOS:
            self._finish()
        elif message.type == Gst.MessageType.ERROR:
            error, debug = message.parse_error()
            name = message.src.get_name() if message.src else ""
            print(f"GStreamer error from {name}: {error.message}\n{debug}")
            if self._error is None:
                self._error = describe_error(name, error, debug)
                if not self._got_video or self._error == "The disk is full.":
                    self._finish()
                else:  # try to close the file properly, but do not wait long
                    self._send_eos(ERROR_STOP_TIMEOUT_SECONDS)
        elif message.type == Gst.MessageType.ELEMENT and self.on_level:
            structure = message.get_structure()
            if structure and structure.get_name() == "level":
                levels = structure.get_value("rms")
                if levels:
                    self.on_level(max(levels))

    def _send_eos(self, timeout):
        self._stopping = True
        self._remove_timer("stop")
        self._pacer.stop()
        self.pipeline.send_event(Gst.Event.new_eos())
        self._timers["stop"] = GLib.timeout_add_seconds(timeout, self._stop_timed_out)

    def _stop_timed_out(self):
        self._timers.pop("stop", None)
        if self._error is None:
            self._error = ("The recorder did not finish in time. The file should "
                           "play, but its last seconds may be missing.")
        self._finish()
        return False

    def _check_started(self):
        self._timers.pop("start", None)
        if not self._got_video and not self._done:
            self._error = ("No picture arrived from the screen. Try choosing the "
                           "screen again.")
            self._finish()
        return False

    def _check_disk(self):
        if self.stopping:
            return True
        try:
            free = disk.free_bytes(os.path.dirname(self.settings.output))
        except OSError:
            self._error = "The recording folder is no longer available."
            self._timers.pop("disk", None)
            self._send_eos(ERROR_STOP_TIMEOUT_SECONDS)
            return False
        limit = self.settings.min_free
        if limit is None:
            limit = disk.stop_threshold(self.bytes_per_hour())
        if free < limit:
            self.stop(f"Stopped because the disk is nearly full "
                      f"({disk.format_size(free)} left).")
        return True

    def _remove_timer(self, name):
        source = self._timers.pop(name, None)
        if source is not None:
            GLib.source_remove(source)

    def _finish(self):
        if self._done:
            return
        self._done = True
        for name in list(self._timers):
            self._remove_timer(name)
        self._bus.remove_signal_watch()
        self._pacer.stop()
        self.pipeline.set_state(Gst.State.NULL)

        path = self.settings.output
        if not self._got_video or self.bytes_written() == 0:
            if os.path.exists(path):
                os.remove(path)  # our own file, with nothing in it
            path = None
            if self._error is None:
                self._error = "Nothing was recorded."
        GLib.idle_add(self._report, path)

    def _report(self, path):
        self.on_finished(path, self._error, self._notice)
        return False
