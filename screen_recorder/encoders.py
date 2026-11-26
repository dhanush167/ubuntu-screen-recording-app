"""H.264 encoder selection (hardware if it works, else x264) and plugin checks."""

import os
from dataclasses import dataclass
from typing import Callable

from gi.repository import Gst

QP = {"low": 28, "medium": 23, "high": 18}


@dataclass(frozen=True)
class Encoder:
    name: str                       # GStreamer element
    label: str
    raw_format: str                 # pixel format fed to the encoder
    options: Callable[[int, int], str]   # (qp, keyframe interval) -> properties
    hardware: bool = True

    def description(self, quality, fps):
        """gst-launch fragment from raw video to H.264 ready for mp4mux."""
        parser = " ! h264parse" if Gst.ElementFactory.find("h264parse") else ""
        return (f"{self.name} {self.options(QP[quality], fps * 2)}{parser} ! "
                "video/x-h264,stream-format=avc,alignment=au")


def _va(qp, gop):
    return f"rate-control=cqp qpi={qp} qpp={qp} qpb={qp} key-int-max={gop} b-frames=0"


def _vaapi(qp, gop):
    return f"rate-control=cqp init-qp={qp} keyframe-period={gop} max-bframes=0"


def _nvenc(qp, gop):
    return f"rc-mode=constqp qp-const={qp} gop-size={gop} bframes=0"


def _x264(qp, gop):
    # x264's default (one thread per 2/3 CPU) holds far more frames in memory
    # on many-core machines and is no faster for desktop-sized video.
    # bframes=0: with reordered frames the MP4 can show video later than audio.
    return (f"pass=qual quantizer={qp} speed-preset=veryfast rc-lookahead=10 bframes=0 "
            f"threads={min(4, os.cpu_count() or 4)} key-int-max={gop}")


CANDIDATES = (
    Encoder("vah264enc", "VA-API (hardware)", "NV12", _va),
    Encoder("vah264lpenc", "VA-API low power (hardware)", "NV12", _va),
    Encoder("vaapih264enc", "VA-API (hardware)", "NV12", _vaapi),
    Encoder("nvh264enc", "NVENC (hardware)", "NV12", _nvenc),
    Encoder("x264enc", "x264 (software)", "I420", _x264, hardware=False),
)


def _works(encoder):
    """Encode a few frames into an MP4 to make sure the whole chain runs."""
    try:
        pipeline = Gst.parse_launch(
            "videotestsrc num-buffers=15 ! "
            f"video/x-raw,format={encoder.raw_format},width=1280,height=720,framerate=30/1 ! "
            f"{encoder.description('medium', 30)} ! "
            "mp4mux fragment-duration=1000 ! fakesink")
    except Exception:  # unknown property or failed link
        return False
    try:
        if pipeline.set_state(Gst.State.PLAYING) == Gst.StateChangeReturn.FAILURE:
            return False
        message = pipeline.get_bus().timed_pop_filtered(
            8 * Gst.SECOND, Gst.MessageType.EOS | Gst.MessageType.ERROR)
        return message is not None and message.type == Gst.MessageType.EOS
    finally:
        pipeline.set_state(Gst.State.NULL)


def pick_encoder():
    """Return the first working encoder, or None."""
    has_parser = Gst.ElementFactory.find("h264parse") is not None
    for encoder in CANDIDATES:
        if encoder.hardware and not has_parser:
            continue
        if Gst.ElementFactory.find(encoder.name) and _works(encoder):
            return encoder
    return None


# element -> Ubuntu package that provides it
_REQUIRED = {
    "pulsesrc": "gstreamer1.0-pulseaudio",
    "audiomixer": "gstreamer1.0-plugins-base",
    "appsrc": "gstreamer1.0-plugins-base",
    "appsink": "gstreamer1.0-plugins-base",
    "videoconvert": "gstreamer1.0-plugins-base",
    "videoscale": "gstreamer1.0-plugins-base",
    "level": "gstreamer1.0-plugins-good",
    "mp4mux": "gstreamer1.0-plugins-good",
    "aacparse": "gstreamer1.0-plugins-good",
    "avenc_aac": "gstreamer1.0-libav",
}


def missing_packages(wayland):
    """Ubuntu packages that must be installed before recording can work."""
    required = dict(_REQUIRED)
    if wayland:
        required["pipewiresrc"] = "gstreamer1.0-pipewire"
    else:
        required["ximagesrc"] = "gstreamer1.0-plugins-good"
    missing = {package for element, package in required.items()
               if Gst.ElementFactory.find(element) is None}
    if not any(Gst.ElementFactory.find(e.name) for e in CANDIDATES):
        missing.add("gstreamer1.0-plugins-ugly")
    return sorted(missing)
