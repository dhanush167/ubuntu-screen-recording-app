#!/usr/bin/python3
"""Record short clips with many settings and check every file.

    /usr/bin/python3 tests/test_recording.py [--keep]
"""

import os
import shutil
import sys
import tempfile

from common import (Settings, decode_errors, devices, encoders, probe, record,
                    stream_span, test_source)

from gi.repository import GLib

from screen_recorder import config, disk
from screen_recorder.recorder import describe_error, quote

SECONDS = 5
failures = []


def check(name, condition, detail=""):
    if not condition:
        failures.append(f"{name}: {detail}")
    return condition


def run_case(name, folder, expected, encoder, pauses=(), seconds=SECONDS,
             check_rate=True, **options):
    options.setdefault("fps", 30)
    path = os.path.join(folder, f"{name}.mp4")
    source = options.pop("source", None) or test_source(fps=60)
    result = record(Settings(output=path, source=source, encoder=encoder, **options),
                    seconds, pauses)
    problems_before = len(failures)
    if not check(name, not result["timed_out"] and result.get("path") == path
                 and not result.get("error"), f"result {result}"):
        print(f"FAIL {name}")
        return
    streams, duration = probe(path)
    audio_on = bool(options.get("mic") or options.get("system"))
    video = streams.get("video", {})
    check(name, video.get("codec_name") == "h264", f"video {video}")
    check(name, abs(duration - expected) < 0.7, f"duration {duration:.2f}, expected {expected}")
    if "video" in streams:
        top, bottom = video["avg_frame_rate"].split("/")
        rate = int(top) / max(1, int(bottom))
        if check_rate:
            check(name, abs(rate - options["fps"]) < 1.5, f"frame rate {rate:.2f}")
    line = f"duration {duration:.2f}s"
    if audio_on:
        sound = streams.get("audio", {})
        if check(name, sound.get("codec_name") == "aac", f"audio {sound}"):
            video_start, video_end = stream_span(path, "video")
            audio_start, audio_end = stream_span(path, "audio")
            check(name, abs(video_start - audio_start) < 0.05,
                  f"video starts {video_start:.3f}, audio {audio_start:.3f}")
            line += f", A/V end difference {abs(video_end - audio_end) * 1000:.0f} ms"
            check(name, abs(video_end - audio_end) < 0.1,
                  f"video ends {video_end:.3f}, audio ends {audio_end:.3f}")
        check(name, result["levels"] > 10, "no audio level updates")
    else:
        check(name, "audio" not in streams, "unexpected audio stream")
    errors = decode_errors(path)
    check(name, not errors, f"decode: {errors[:300]}")
    status = "ok  " if len(failures) == problems_before else "FAIL"
    print(f"{status} {name:28} {video.get('width')}x{video.get('height')}  {line}")


def main():
    keep = "--keep" in sys.argv
    folder = tempfile.mkdtemp(prefix="recorder-test-")
    encoder = encoders.pick_encoder()
    if encoder is None:
        sys.exit("No working H.264 encoder.")
    mic, system = devices()
    print(f"encoder: {encoder.name}\nmicrophone: {mic}\nsystem audio: {system}\n")
    both = {"mic": mic, "system": system}

    for fps in config.FRAME_RATES:
        for quality in config.QUALITIES:
            run_case(f"{fps}fps_{quality}", folder, SECONDS, encoder,
                     fps=fps, quality=quality, **both)
    run_case("mic_only", folder, SECONDS, encoder, mic=mic)
    run_case("system_only", folder, SECONDS, encoder, system=system)
    run_case("no_audio", folder, SECONDS, encoder)
    # A still screen sends very few frames; the file must still be full rate.
    run_case("still_screen", folder, SECONDS, encoder,
             source="videotestsrc name=screen is-live=true ! "
                    "video/x-raw,width=1280,height=720,framerate=1/4", **both)
    # The first picture arriving late must not push the video behind the audio.
    run_case("late_first_frame", folder, SECONDS, encoder, check_rate=False,
             source="videotestsrc name=screen is-live=true ! "
                    "video/x-raw,width=1280,height=720,framerate=2/1 ! "
                    "identity sleep-time=600000", **both)
    run_case("single_frame", folder, SECONDS, encoder,
             source="videotestsrc name=screen is-live=true num-buffers=1 ! "
                    "video/x-raw,width=1280,height=720,framerate=30/1", **both)
    run_case("odd_size", folder, SECONDS, encoder, source=test_source(1367, 769), **both)
    run_case("pause_once", folder, 5, encoder, pauses=[(2, 5)], seconds=8, **both)
    run_case("pause_twice", folder, 6, encoder, pauses=[(2, 4), (6, 7)], seconds=9, **both)
    run_case("pause_no_audio", folder, 5, encoder, pauses=[(2, 4)], seconds=7)
    run_case("stop_while_paused", folder, 3, encoder, pauses=[(3, 99)], seconds=5, **both)

    # The recording must stop by itself, with a valid file, when space runs out.
    path = os.path.join(folder, "disk_guard.mp4")
    free = disk.free_bytes(folder)
    result = record(Settings(output=path, source=test_source(), encoder=encoder,
                             min_free=free * 2, **both), 30)
    good = (result.get("path") == path and not result.get("error")
            and "disk is nearly full" in (result.get("notice") or "")
            and not decode_errors(path))
    check("disk_guard", good, str(result))
    print(f"{'ok  ' if good else 'FAIL'} disk_guard                   {result.get('notice')}")

    # Errors must be reported, and no empty file left behind.
    message = describe_error("mic", GLib.Error("Could not open resource"), "")
    check("microphone_message", "microphone" in message, message)
    for name, options, expected in (
            ("bad_screen", {"source": "filesrc name=screen location="
                            + quote("/no/such/file")}, "Screen capture"),
            ("unwritable", {"output": "/proc/recorder-test.mp4"}, "")):
        values = dict(output=os.path.join(folder, f"{name}.mp4"),
                      source=test_source(), encoder=encoder)
        values.update(options)
        result = record(Settings(**values), 4)
        good = bool(result.get("error")) and expected.lower() in result["error"].lower()
        check(name, good and not result["timed_out"], str(result))
        print(f"{'ok  ' if good else 'FAIL'} {name:28} {result.get('error')}")

    if keep or failures:
        print(f"\nfiles kept in {folder}")
    else:
        shutil.rmtree(folder)
    print("\n" + ("ALL TESTS PASSED" if not failures else
                  "FAILURES:\n  " + "\n  ".join(failures)))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
