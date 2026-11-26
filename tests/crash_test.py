#!/usr/bin/python3
"""Kill the recorder mid-recording (like a crash) and check the file plays.

    /usr/bin/python3 tests/crash_test.py
"""

import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time

from common import Settings, devices, encoders, probe, record, test_source

RUN_SECONDS = 20
MAX_LOSS_SECONDS = 5


def main():
    if len(sys.argv) > 2 and sys.argv[1] == "--child":
        mic, system = devices()
        record(Settings(output=sys.argv[2], source=test_source(),
                        encoder=encoders.pick_encoder(), mic=mic, system=system), 600,
               on_start=lambda _r: print("started", flush=True))
        return 0

    folder = tempfile.mkdtemp(prefix="recorder-crash-")
    path = os.path.join(folder, "crash.mp4")
    child = subprocess.Popen([sys.executable, os.path.abspath(__file__), "--child", path],
                             stdout=subprocess.PIPE, text=True)
    try:
        if child.stdout.readline().strip() != "started":
            sys.exit("The recording did not start.")
        time.sleep(RUN_SECONDS)
    finally:
        child.send_signal(signal.SIGKILL)
        child.wait()

    streams, duration = probe(path)
    # A kill can cut the very last fragment in half; players skip that part.
    decode = subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-f", "null", "-"],
                            capture_output=True, text=True)
    ok = (decode.returncode == 0 and "video" in streams and "audio" in streams
          and duration >= RUN_SECONDS - MAX_LOSS_SECONDS)
    print(f"killed after {RUN_SECONDS}s: {duration:.1f}s playable, "
          f"streams {sorted(streams)}, decoder exit {decode.returncode}")
    if decode.stderr:
        print("decoder notes:", decode.stderr.strip()[:300])
    print("CRASH TEST PASSED" if ok else f"CRASH TEST FAILED (file kept at {path})")
    if ok:
        shutil.rmtree(folder)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
