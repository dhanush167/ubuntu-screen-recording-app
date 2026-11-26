#!/usr/bin/python3
"""Long recording with CPU, memory and A/V sync measurements.

    /usr/bin/python3 tests/soak.py --minutes 10 [--output-dir DIR]

The picture is a 1920x1200 test pattern, so CPU use is close to a real screen
recording (a real desktop is usually easier to encode).
"""

import argparse
import contextlib
import os
import subprocess
import sys

from gi.repository import GLib

from common import (Settings, decode_errors, devices, encoders, pipewire_screen,
                    probe, record, stream_span, test_source)


def resident_megabytes():
    with open("/proc/self/status", encoding="utf-8") as handle:
        for line in handle:
            if line.startswith("VmRSS:"):
                return int(line.split()[1]) / 1024
    return 0.0


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--minutes", type=float, default=10)
    parser.add_argument("--output-dir", default=".")
    parser.add_argument("--interval", type=int, default=30)
    parser.add_argument("--pipewire", action="store_true",
                        help="feed the picture through pipewiresrc, as on Wayland")
    args = parser.parse_args()

    path = os.path.join(os.path.abspath(args.output_dir), "soak.mp4")
    if os.path.exists(path):
        sys.exit(f"{path} already exists; move it away first.")
    encoder = encoders.pick_encoder()
    mic, system = devices()
    print(f"{args.minutes} min, 1920x1200@30, {encoder.name}, {os.cpu_count()} CPUs",
          flush=True)
    samples = []

    def watch(recording):
        last = [os.times()]

        def sample():
            now, before = os.times(), last[0]
            last[0] = now
            cpu = 100 * ((now.user + now.system) - (before.user + before.system)) \
                / (now.elapsed - before.elapsed)
            row = (recording.elapsed(), cpu, resident_megabytes(),
                   recording.bytes_written() / 1e6)
            samples.append(row)
            print("t={:6.0f}s  cpu={:5.0f}%  rss={:6.0f} MB  file={:8.1f} MB".format(*row),
                  flush=True)
            return not recording.stopping

        GLib.timeout_add_seconds(args.interval, sample)

    screen = (pipewire_screen(1920, 1200) if args.pipewire
              else contextlib.nullcontext(test_source(1920, 1200)))
    with screen as source:
        result = record(Settings(output=path, source=source, encoder=encoder,
                                 mic=mic, system=system),
                        args.minutes * 60, on_start=watch)
    if result.get("error") or result["timed_out"]:
        sys.exit(f"Recording failed: {result}")

    streams, duration = probe(path)
    spans = {kind: stream_span(path, kind) for kind in streams}
    start_gap = abs(spans["video"][0] - spans["audio"][0]) * 1000
    drift = abs(spans["video"][1] - spans["audio"][1]) * 1000
    errors = decode_errors(path)
    stable = samples[len(samples) // 3:]
    growth = stable[-1][2] - stable[0][2] if len(stable) > 1 else 0.0
    cpu = sum(s[1] for s in samples) / max(1, len(samples))
    print(f"\nduration {duration:.2f}s (asked {args.minutes * 60:.0f}s)")
    print(f"A/V start difference {start_gap:.0f} ms, end difference {drift:.0f} ms")
    print(f"average CPU {cpu:.0f}% of one core, memory change after warm-up {growth:+.0f} MB")
    print(f"decode errors: {errors[:300] or 'none'}")
    smooth = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v", "-count_packets",
         "-show_entries", "stream=nb_read_packets", "-of", "csv=p=0", path],
        capture_output=True, text=True).stdout.strip()
    expected = duration * 30
    dropped = max(0.0, 100 * (1 - int(smooth) / expected))
    print(f"video frames {smooth} of about {expected:.0f} ({dropped:.2f}% dropped)")
    ok = (start_gap < 50 and drift < 100 and not errors and abs(duration - args.minutes * 60) < 3
          and growth < 50 and dropped < 1)
    print("SOAK TEST PASSED" if ok else "SOAK TEST FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
