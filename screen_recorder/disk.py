"""Free space and recording size estimates."""

import os
import shutil

GB = 1000 ** 3
SOAK_HOURS = 4

# Typical bits per pixel for desktop content at 30 fps. Used only until the
# real size of the running recording is known.
BITS_PER_PIXEL = {"low": 0.025, "medium": 0.045, "high": 0.085}
AUDIO_BITRATE = {"low": 128000, "medium": 160000, "high": 192000}

MINIMUM_FREE = 1 * GB
RESERVE_SECONDS = 180


def free_bytes(folder):
    """Free space available at `folder`, which does not need to exist yet."""
    path = os.path.abspath(folder)
    while not os.path.exists(path):
        path = os.path.dirname(path)
    return shutil.disk_usage(path).free


def estimate_per_hour(width, height, fps, quality, audio=True):
    """Estimated bytes written per hour of recording."""
    # Lower frame rates save less than proportionally: frames differ more.
    video = width * height * 30 * BITS_PER_PIXEL[quality] * (0.4 + 0.6 * fps / 30)
    sound = AUDIO_BITRATE[quality] if audio else 0
    return int((video + sound) * 3600 / 8)


def stop_threshold(per_hour):
    """Recording stops when free space falls below this many bytes."""
    return max(MINIMUM_FREE, int(per_hour * RESERVE_SECONDS / 3600))


def hours_left(free, per_hour):
    return max(0.0, (free - stop_threshold(per_hour)) / max(1, per_hour))


def format_size(size):
    for unit, scale in (("GB", GB), ("MB", 1000 ** 2)):
        if size >= scale:
            value = size / scale
            return f"{value:.0f} {unit}" if value >= 100 else f"{value:.1f} {unit}"
    return f"{size / 1000:.0f} kB"
