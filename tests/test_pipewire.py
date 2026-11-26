#!/usr/bin/python3
"""Record through pipewiresrc, the element used for the screen on Wayland.

    /usr/bin/python3 tests/test_pipewire.py

A temporary PipeWire video source (a test picture) stands in for the screen, so
no permission dialog appears. Needs gstreamer1.0-tools and pipewire-bin.
Each case runs in its own process.
"""

import os
import shutil
import subprocess
import sys
import tempfile

from common import (Settings, decode_errors, devices, encoders, pipewire_screen,
                    probe, record, stream_span)

SECONDS = 20


def run_case(rate):
    folder = tempfile.mkdtemp(prefix="recorder-pipewire-")
    with pipewire_screen(1281, 721, rate) as source:
        mic, system = devices()
        path = os.path.join(folder, "pipewire.mp4")
        result = record(Settings(output=path, source=source,
                                 encoder=encoders.pick_encoder(), mic=mic, system=system),
                        SECONDS, pauses=[(8, 10)])
    expected = SECONDS - 2
    if result.get("error") or result["timed_out"] or not result.get("path"):
        print(f"FAIL source at {rate}: {result}")
        return 1
    streams, duration = probe(path)
    video = streams["video"]
    top, bottom = video["avg_frame_rate"].split("/")
    fps = int(top) / int(bottom)
    (video_start, video_end), (audio_start, audio_end) = (
        stream_span(path, "video"), stream_span(path, "audio"))
    start_gap, end_gap = abs(video_start - audio_start), abs(video_end - audio_end)
    errors = decode_errors(path)
    ok = (abs(duration - expected) < 0.7 and abs(fps - 30) < 1.5
          and start_gap < 0.05 and end_gap < 0.1 and not errors)
    print(f"{'ok  ' if ok else 'FAIL'} source at {rate:5} duration {duration:.2f}s "
          f"(expected {expected}), {fps:.1f} fps, A/V start/end difference "
          f"{start_gap * 1000:.0f}/{end_gap * 1000:.0f} ms, "
          f"decode {errors[:200] or 'clean'}")
    if ok:
        shutil.rmtree(folder)
    return 0 if ok else 1


def main():
    if len(sys.argv) == 3 and sys.argv[1] == "--case":
        return run_case(sys.argv[2])
    failed = 0
    for rate in ("30/1", "2/1"):   # a busy screen and a nearly still one
        failed += subprocess.run(
            [sys.executable, os.path.abspath(__file__), "--case", rate]).returncode
    print("PIPEWIRE TEST PASSED" if not failed else "PIPEWIRE TEST FAILED")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
