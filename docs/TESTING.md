# Test checklist

Run these on the real screen, because the automated tests cannot press the
desktop's screen-sharing dialog.

## 0. Automated tests (no clicks needed)

```bash
cd /opt/lampp/htdocs/video_recorder
```

```bash
/usr/bin/python3 tests/test_recording.py
```

```bash
/usr/bin/python3 tests/test_pipewire.py
```

```bash
/usr/bin/python3 tests/crash_test.py
```

```bash
/usr/bin/python3 tests/ui_test.py
```

```bash
/usr/bin/python3 tests/soak.py --pipewire --minutes 10 --output-dir /tmp
```

The tests record from your real microphone and speakers and use a test picture
instead of the screen; `test_pipewire.py` and `soak.py --pipewire` send it
through the same PipeWire element that Wayland screen capture uses (they need
`gstreamer1.0-tools` and `pipewire-bin`). `soak.py` refuses to overwrite an
existing `soak.mp4`.

## Tools for the manual tests

```bash
sudo apt install vlc ffmpeg
```

Make a sync clip: a white flash and a beep every 5 seconds.

```bash
ffmpeg -f lavfi -i "color=black:s=1280x720:r=30:d=60,drawbox=color=white:t=fill:enable='lt(mod(t,5),0.2)'" -f lavfi -i "sine=frequency=1000:duration=60,volume='if(lt(mod(t,5),0.2),1,0)':eval=frame" -c:v libx264 -pix_fmt yuv420p -c:a aac -shortest ~/sync-test.mp4
```

Log CPU and memory once a minute while recording (stop with Ctrl+C):

```bash
while sleep 60; do ps -o etime=,pcpu=,rss= -p "$(pgrep -f -o 'm screen_recorder')" | tee -a ~/recorder-usage.log; done
```

`pcpu` is the average since the app started, in percent of one core; `rss` is
memory in kB. For a live view use `top -p "$(pgrep -f -o 'm screen_recorder')"`.

Check a finished file (replace `FILE.mp4`):

```bash
ffprobe -v error -show_entries format=duration:stream=codec_name,width,height,avg_frame_rate,duration -of compact FILE.mp4
```

```bash
ffmpeg -v error -i FILE.mp4 -f null -
```

The second command should print nothing.

## 1. One-minute test

- [ ] Start the app, tick Microphone and System audio, press **Start**, pick the screen.
- [ ] The level bar moves when you speak and when sound plays.
- [ ] Play `~/sync-test.mp4` full screen with sound, then say a few words.
- [ ] Press **Pause**, wait 10 s, press **Resume**; the timer must not advance while paused.
- [ ] Press **Stop**. "Saved!" appears, with a notification; **Open folder** and **Play** work.
- [ ] In VLC: picture is sharp, both your voice and the computer sound are audible,
      flash and beep happen together, the 10 s pause is not in the file.
- [ ] Press Ctrl+Alt+R in another app: recording starts. Press it again: it stops.
- [ ] With two monitors: press **Choose…**, pick the other monitor and press
      **Share**. The Screen row names it (for example "HDMI-1 · 1366×768"), and the
      next recording shows that monitor, without asking again.
- [ ] Repeat once with only Microphone, and once with only System audio.

## 2. Ten-minute test

- [ ] Start the usage log. Record 10 minutes of normal work.
- [ ] Play the sync clip during the first minute and again in the last minute.
- [ ] Leave the computer untouched for part of the time: the screen must not lock.
- [ ] File duration matches the timer (within 2 s).
- [ ] In VLC, seek to the start, middle and end; both sync checks look the same.
- [ ] Memory after minute 10 is within 50 MB of memory at minute 2.
- [ ] Footer's "per hour" figure matches the real file size reasonably well.
- [ ] Crash check: during a new recording run `pkill -9 -f 'm screen_recorder'`.
      The file in `~/Videos/Recordings` still plays up to a few seconds before the kill.

## 3. Four-hour soak test

Before starting: plug in the charger, check the footer shows room for well over
4 hours, and close nothing you normally use.

- [ ] Start the usage log and a recording. Play the sync clip in minute 1.
- [ ] Play it again at about 1 h, 2 h, 3 h and just before stopping.
- [ ] Use Pause/Resume a few times along the way.
- [ ] Stop after at least 4 h. Saving should take only a few seconds.
- [ ] `ffprobe` duration matches the timer (within 5 s).
- [ ] `ffmpeg -v error ... -f null -` prints nothing (takes several minutes).
- [ ] In VLC, jump to each sync clip: flash and beep are still together at 4 h.
      Seeking anywhere in the file works.
- [ ] Memory stayed flat (no steady climb in the log); CPU stayed steady and the
      desktop remained responsive.

What to expect for CPU at 1920×1200, 30 fps (measured on a 14-thread Intel laptop;
Settings shows which encoder is in use):

- Software encoder (x264): about 1 core for a mostly still screen and up to
  2–2.5 cores while lots of the screen moves (video playing, scrolling).
- Hardware encoder (VA-API, used after `./install.sh`): the encoding itself
  costs almost no CPU; capturing and converting the picture remain.

Memory with the software encoder is about 400–500 MB; what matters is that it
stays flat over time.
