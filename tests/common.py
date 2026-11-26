"""Shared helpers. Tests replace the screen with a moving test picture, so they
need no permission dialog; audio comes from the real default devices."""

import contextlib
import json
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from gi.repository import GLib  # noqa: E402

from screen_recorder import audio, encoders  # noqa: E402,F401
from screen_recorder.recorder import (Recording, Settings,  # noqa: E402
                                      wayland_source)


def test_source(width=1280, height=720, fps=30):
    return ("videotestsrc name=screen is-live=true pattern=ball motion=sweep ! "
            f"video/x-raw,width={width},height={height},framerate={fps}/1")


def devices():
    mics, outputs = audio.list_devices()
    return (mics[0].id if mics else None), (outputs[0].id if outputs else None)


def record(settings, seconds, pauses=(), on_start=None):
    """Record for `seconds` of wall time. pauses = [(from, to), ...] in seconds."""
    loop = GLib.MainLoop()
    result = {"levels": 0, "timed_out": False}

    def finished(path, error, notice):
        result.update(path=path, error=error, notice=notice)
        loop.quit()

    def level(_decibels):
        result["levels"] += 1

    recording = Recording(settings, finished, level)

    def once(delay, action):
        def run():
            action()
            return False
        return GLib.timeout_add(int(delay * 1000), run)

    recording.start()
    for begin, end in pauses:
        once(begin, lambda: recording.set_paused(True))
        once(end, lambda: recording.set_paused(False))
    once(seconds, recording.stop)

    def give_up():
        result["timed_out"] = True
        loop.quit()

    once(seconds + 40, give_up)
    if on_start:
        on_start(recording)
    loop.run()
    result["size"] = recording.size
    return result


def probe(path):
    """Return ({codec_type: stream}, container duration) using ffprobe."""
    output = subprocess.run(
        ["ffprobe", "-v", "error", "-of", "json", "-show_entries",
         "format=duration:stream=codec_type,codec_name,width,height,duration,"
         "avg_frame_rate,start_time", path],
        capture_output=True, text=True, check=True).stdout
    data = json.loads(output)
    streams = {s["codec_type"]: s for s in data["streams"]}
    return streams, float(data["format"]["duration"])


def decode_errors(path):
    """Decode the whole file and return whatever FFmpeg complains about."""
    return subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-f", "null", "-"],
                          capture_output=True, text=True).stderr.strip()


def stream_span(path, kind):
    """(first, end) presentation times of a stream, read from its packets."""
    output = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", kind[0], "-show_entries",
         "packet=pts_time,duration_time", "-of", "csv=p=0", path],
        capture_output=True, text=True, check=True).stdout
    rows = [line.split(",")[:2] for line in output.split() if line]
    starts = [float(pts) for pts, _ in rows]
    ends = [float(pts) + float(length) for pts, length in rows]
    return min(starts), max(ends)


@contextlib.contextmanager
def pipewire_screen(width, height, rate="30/1"):
    """A temporary PipeWire video source standing in for the real screen.

    Yields the same source the app uses on Wayland. Connect to it once per
    process. Needs gstreamer1.0-tools and pipewire-bin.
    """
    name = f"recorder-test-source-{os.getpid()}"
    feeder = subprocess.Popen(
        ["gst-launch-1.0", "-q", "videotestsrc", "is-live=true", "pattern=ball", "!",
         f"video/x-raw,format=BGRx,width={width},height={height},framerate={rate}",
         "!", "pipewiresink", "mode=provide",
         f"stream-properties=props,media.class=Video/Source,node.name={name}"],
        stdout=subprocess.DEVNULL)
    try:
        time.sleep(1.5)
        nodes = json.loads(subprocess.run(["pw-dump"], capture_output=True, text=True,
                                          check=True).stdout)
        found = [n["id"] for n in nodes
                 if n.get("info", {}).get("props", {}).get("node.name") == name]
        if not found:
            raise RuntimeError("The PipeWire test source did not appear.")
        # No portal here, so there is no private PipeWire connection (fd).
        yield wayland_source(0, found[0]).replace("fd=0 ", "")
        if feeder.poll() is not None:
            # gst-launch's pipewiresink occasionally crashes; then the file
            # holds a frozen picture and proves nothing.
            raise RuntimeError("The PipeWire test source stopped during the test; "
                               "run it again.")
    finally:
        feeder.kill()
        feeder.wait()
