"""Turn irregular screen frames into a steady frame rate.

PipeWire sends a frame only when the screen changes. pipewiresrc's own
"keepalive-time" option is meant to fill the gaps, but on PipeWire 1.0
(Ubuntu 24.04) it freezes the stream after a few seconds and the recording can
no longer be stopped. So the newest frame is repeated here instead.
"""

import re
import threading

from gi.repository import Gst

MAX_LAG = Gst.SECOND   # further behind than this (after a suspend): skip ahead


class FramePacer:
    """Take frames from appsink "grab" and feed appsrc "feed" at `fps`."""

    def __init__(self, pipeline, fps):
        self.pipeline = pipeline
        self.fps = fps
        self.source = pipeline.get_by_name("feed")
        self._latest = None
        self._thread = None
        self._stopped = threading.Event()
        pipeline.get_by_name("grab").connect("new-sample", self._on_sample)

    def _on_sample(self, sink):
        sample = sink.emit("pull-sample")
        if sample is None or self._stopped.is_set():
            return Gst.FlowReturn.OK
        self._latest = sample.get_buffer()
        if self._thread is None:
            # Same picture format, but announced at the steady frame rate.
            caps = re.sub(r",\s*(?:max-)?framerate=\(fraction\)[0-9/]+", "",
                          sample.get_caps().to_string())
            caps = f"{caps}, framerate=(fraction){self.fps}/1"
            self.source.set_property("caps", Gst.Caps.from_string(caps))
            self._thread = threading.Thread(target=self._run, name="frame-pacer",
                                            daemon=True)
            self._thread.start()
        return Gst.FlowReturn.OK

    def stop(self):
        """Stop producing frames and end the video stream."""
        if self._stopped.is_set():
            return
        self._stopped.set()
        if self._thread is not None:
            self._thread.join(timeout=2)
        self.source.emit("end-of-stream")

    def _time_of(self, frame):
        return frame * Gst.SECOND // self.fps

    def _running_time(self):
        clock = self.pipeline.get_clock()
        if clock is None:
            return None
        return max(0, clock.get_time() - self.pipeline.get_base_time())

    def _push(self, start, end):
        latest = self._latest
        # A new buffer object sharing the same picture data, with its own times.
        frame = latest.copy_region(
            Gst.BufferCopyFlags.FLAGS | Gst.BufferCopyFlags.MEMORY
            | Gst.BufferCopyFlags.META, 0, latest.get_size())
        frame.pts = start
        frame.duration = end - start
        return self.source.emit("push-buffer", frame) == Gst.FlowReturn.OK

    def _run(self):
        now = self._running_time()
        while now is None:
            if self._stopped.wait(0.01):
                return
            now = self._running_time()
        # The first picture covers the time from the start of the recording.
        number = now * self.fps // Gst.SECOND + 1
        if not self._push(0, self._time_of(number)):
            return
        while True:
            now = self._running_time()
            if now is None:
                return
            due = self._time_of(number)
            if now < due:
                if self._stopped.wait((due - now) / Gst.SECOND):
                    return
                continue
            if self._stopped.is_set():
                return
            if now - due > MAX_LAG:
                number = now * self.fps // Gst.SECOND
            if not self._push(self._time_of(number), self._time_of(number + 1)):
                return
            number += 1
