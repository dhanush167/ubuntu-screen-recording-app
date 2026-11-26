# Screen Recorder for Ubuntu

<img width="1299" height="731" alt="Screenshot from 2026-11-26 15-29-44" src="https://github.com/user-attachments/assets/05bd57c2-b1e0-4c34-a531-69c0d855084c" />


A simple desktop app that records your screen together with your microphone
and/or your computer's sound, and saves it as an **MP4** video that plays
everywhere.

It is made for long recordings (lectures, meetings, tutorials): it is built to
run for **4 hours or more** without crashing, drifting out of sync or losing
the file.

- Works on **Ubuntu 24.04 LTS** (tested) and **Ubuntu 25.x** (not yet tested)
- GNOME desktop, on **Wayland** (Ubuntu's default) or **X11 / Xorg**
- No account, no internet connection, no cloud: everything stays on your computer

---

## Contents

1. [Features](#features)
2. [What you need](#what-you-need)
3. [Install](#install)
4. [First start](#first-start)
5. [How to record](#how-to-record)
6. [Settings](#settings)
7. [Where your recordings go](#where-your-recordings-go)
8. [Long recordings and disk space](#long-recordings-and-disk-space)
9. [Privacy and security](#privacy-and-security)
10. [Update or uninstall](#update-or-uninstall)
11. [Troubleshooting](#troubleshooting)
12. [For developers](#for-developers)
13. [License](#license)

---

## Features

- **One small window** with Start, Pause/Resume and Stop, and a running timer
- **Record a whole screen.** With several monitors, you choose which one.
- **Audio:** microphone, computer sound (what you hear), or both mixed together
- **MP4 output** (H.264 video + AAC audio) that plays in VLC, browsers, phones
  and video editors
- **Frame rate** 15, 24 or 30 fps; **quality** Low, Medium or High
- **Global hotkey** (default **Ctrl+Alt+R**) to start and stop from any app
- **"Saved!" notification** with **Open folder** and **Play** buttons
- **Disk space check:** shows free space and size per hour, warns before a long
  recording will not fit, and stops safely before the disk is full
- **Crash-safe files:** if the computer crashes or loses power, the recording
  still plays, up to the last few seconds
- **Uses your graphics chip for video encoding** when it can, so the computer
  stays fast

---

## What you need

- Ubuntu 24.04 or newer, with the normal GNOME desktop
- An internet connection **during installation only** (to download the parts
  Ubuntu needs)
- Your password, for installing (the app itself never needs it)
- Free disk space for your recordings: about **0.5–2 GB per hour** at Medium
  quality, depending on how much moves on screen

To check which Ubuntu you have, open **Terminal** (press **Ctrl+Alt+T**) and run:

```bash
lsb_release -d
```

---

## Install

You only need to copy and paste a few commands. To open a terminal, press
**Ctrl+Alt+T**.

### Option A: install from the source code (recommended)

**1. Install Git** (the tool that downloads the code). Skip this if you already
have it:

```bash
sudo apt install -y git
```

**2. Download the app.** Replace `YOUR-GITHUB-NAME` with the GitHub account
that publishes this app:

```bash
git clone https://github.com/YOUR-GITHUB-NAME/screen-recorder.git
```

```bash
cd screen-recorder
```

(No Git? On the GitHub page click **Code → Download ZIP**, unzip it, then
right-click the unzipped folder and choose **Open in Terminal**.)

**3. Install:**

```bash
./install.sh
```

Type your password when asked. Nothing appears on screen while you type, which
is normal. The installer:

- builds an installable package (`dist/screen-recorder_1.0.0_all.deb`)
- installs it with Ubuntu's own package manager, which also downloads
  everything the app needs (GStreamer, PipeWire support, codecs)

It takes a minute or two. When you see **"Installed."**, you are done.

### Option B: install a ready-made package

If the GitHub page has a **Releases** section with a file named
`screen-recorder_1.0.0_all.deb`, download it, open a terminal in your
**Downloads** folder and run:

```bash
sudo apt install ./screen-recorder_1.0.0_all.deb
```

Use `apt` as shown rather than double-clicking the file: `apt` also installs
the parts the app needs.

### Option C: try it without installing

To run it straight from the downloaded folder:

```bash
./run.sh
```

This needs the packages in [requirements.txt](requirements.txt) to be
installed already. Notification buttons work only in the installed version.

---

## First start

1. Open the app list (press the **Super/Windows** key), type **Screen
   Recorder** and click it. Or run `screen-recorder` in a terminal.
2. After a moment the window shows **Ready** and the video encoder in use,
   for example *VA-API (hardware)* or *x264 (software)*.
3. **Choose your screen** (see below). You only do this once; it is remembered.
4. **Tick the audio boxes** you want.
5. **Make a short test recording** (10 seconds) and play it, to check picture
   and sound before recording something important.

---

## How to record

The window, from top to bottom: **Screen** (with **Choose…**),
**Microphone** and **System audio** tick boxes, the timer, a sound-level bar,
the **Start / Pause / Stop** buttons, and **Save to** with **Change folder**.

### 1. Choose the screen

**Wayland (Ubuntu's default):**

1. Next to **Screen**, press **Choose…**
2. Ubuntu shows its screen-sharing dialog. Click the monitor you want to
   record, keep **Remember this selection** on, and press **Share**.
3. The **Screen** row now names your choice, for example
   *HDMI-1 · 1366×768* or *eDP-1 · 1920×1200* (eDP is the built-in laptop
   screen).

You can skip this step: then the dialog appears when you press Start. To
record a different monitor later, press **Choose…** again.

**X11 / Xorg:** pick the monitor from the **Screen** list.

> Not sure which session you use? Run `echo $XDG_SESSION_TYPE` in a terminal.

### 2. Choose the audio

| Tick box           | Records                                               |
| ------------------ | ----------------------------------------------------- |
| **Microphone**     | your voice (built-in mic, headset, USB microphone)    |
| **System audio**   | everything your computer plays (videos, calls, music) |
| both               | both, mixed together                                  |
| neither            | video only, no sound                                  |

Leave the device list on **Default** to use the device chosen in Ubuntu's
**Settings → Sound**, or pick a specific one. The bar under the timer moves
when sound is being picked up.

> **Tip:** if you record the microphone *and* system audio, use headphones.
> Otherwise the microphone also picks up your speakers and you hear an echo.

### 3. Record

| Button / key        | What it does                                                      |
| ------------------- | ----------------------------------------------------------------- |
| **Start**           | begins recording; the timer starts                                |
| **Pause / Resume**  | pauses; the paused part is left out of the video                  |
| **Stop**            | finishes and saves the file                                       |
| **Ctrl+Alt+R**      | starts or stops from any app, even when the window is minimised  |

While recording you will see GNOME's orange **screen-sharing icon** in the top
bar. You can also stop the recording from there; the file is saved the same
way.

Your computer will not lock the screen or go to sleep on its own while a
recording is running.

### 4. Watch it

When you press Stop, **Saved!** appears in the window and as a desktop
notification, with two buttons:

- **Play** opens the video in your video player
- **Open folder** shows the file in the file manager

---

## Settings

Click the **gear** button at the top of the window.

| Setting         | Choices                  | Advice                                                                                       |
| --------------- | ------------------------ | -------------------------------------------------------------------------------------------- |
| **Frame rate**  | 15, 24, 30 fps           | 30 for smooth motion (default); 15 for slides and documents, which also saves space and CPU  |
| **Quality**     | Low, Medium, High        | Medium suits most uses (default); High for small text; Low for very long recordings          |
| **Encoder**     | shown, not changeable    | *hardware* is best; see [Troubleshooting](#troubleshooting) if it says *software*            |
| **Hotkey**      | any key combination      | press **Change**, then the new keys; **Turn off** removes it                                 |

The **save folder** is changed in the main window with **Change folder**.

Settings are kept in `~/.config/screen-recorder/settings.json`.

> The global hotkey is added to GNOME's own keyboard shortcuts, as
> *Screen Recorder: start/stop* in **Settings → Keyboard → View and
> Customise Shortcuts → Custom Shortcuts**. It works on GNOME only, and also
> starts the app if it is not open.

---

## Where your recordings go

```
~/Videos/Recordings/Recording_2026-11-26_14-30-05.mp4
```

Each file is named after the date and time the recording started, so nothing
is ever overwritten.

---

## Long recordings and disk space

The line at the bottom of the window shows, for example:

```
Free 208 GB · about 1.5 GB per hour · room for over 99 h
```

- The **per hour** figure is an estimate for the first minute, then it is
  measured from the real recording.
- A **warning** appears at the top if there is not enough space for 4 hours.
- If space runs low during a recording, it **stops by itself and saves the
  file** when less than 1 GB (or about 3 minutes' worth) is left.

Before a long recording:

1. Plug in the charger.
2. Check the footer shows room for longer than you need.
3. Make a 1-minute test recording and play it back.
4. Close apps you do not need (fewer pop-ups, less CPU).

**If the computer crashes or loses power**, the MP4 is still there and plays up
to the last few seconds. It is written in one-second pieces, so there is
nothing to repair.

---

## Privacy and security

- **Nothing leaves your computer.** The app has no network features, no
  tracking and no accounts.
- **You always give permission to record the screen** through Ubuntu's own
  sharing dialog, and the orange top-bar icon shows when recording is on.
  To make the app ask every time, press **Choose…** and switch off
  **Remember this selection**.
- **The app runs as your normal user.** Only `install.sh` and `uninstall.sh` use
  `sudo`, to install or remove the package with `apt`.
- **Recordings contain whatever is on screen and in the audio:** passwords
  you type, messages, notifications, call audio. Use **Pause** before
  showing anything private, and turn on **Do Not Disturb** to avoid
  notification pop-ups.
- **Who can open your recordings:** they are saved as normal files in your
  home folder, which other user accounts on the computer cannot open by
  default on Ubuntu. If you choose a save folder outside your home folder
  (for example a shared drive), other users of the computer may be able to
  open them.

---

## Update or uninstall

**Update** to a newer version (in the folder you downloaded):

```bash
git pull
```

```bash
./install.sh
```

**Uninstall:**

```bash
./uninstall.sh
```

This removes the app and its hotkey. **Your recordings are not deleted.** Your
settings stay in `~/.config/screen-recorder`; delete that folder too if you
want a clean removal:

```bash
rm -r ~/.config/screen-recorder
```

---

## Troubleshooting

To see detailed messages, start the app from a terminal:

```bash
screen-recorder
```

### The screen dialog does not appear, or "Screen capture is not available"

Restart the services involved:

```bash
systemctl --user restart pipewire wireplumber xdg-desktop-portal-gnome xdg-desktop-portal
```

If that does not help, log out and back in.

### It records the wrong monitor

Press **Choose…**, pick the right monitor and press **Share**. The Screen row
shows which one will be recorded.

### "No picture arrived from the screen"

Press **Choose…** and pick the screen again. With NVIDIA graphics on Wayland,
update the driver, or choose **Ubuntu on Xorg** on the login screen (gear icon
at the bottom right).

### No computer sound in the recording

- Tick **System audio**.
- Leave it on **Default**, or pick the output you actually listen on
  (speakers, headphones, HDMI).
- Check that **Settings → Sound → Output** is the device that plays the sound.

### Microphone is silent, or "No microphone found"

- Check **Settings → Sound → Input**: correct device, not muted, level above zero.
- Plug in the microphone, then click the app window again; the list refreshes.
- Untick **Microphone** to record without it.

### "Some components are missing"

The window shows the exact `sudo apt install …` command to run. Running
`./install.sh` again also fixes it.

### Settings shows "x264 (software)" and the computer gets slow

Your graphics chip is not being used for encoding. For Intel and AMD graphics:

```bash
sudo apt install gstreamer1.0-plugins-bad gstreamer1.0-vaapi intel-media-va-driver mesa-va-drivers
```

Then clear GStreamer's cache and restart the app:

```bash
rm -r ~/.cache/gstreamer-1.0
```

Lowering the frame rate to 15 or 24 also helps.

### The hotkey does nothing

- Check that it appears in GNOME's Custom Shortcuts (see [Settings](#settings)).
- Pick a different combination in the app's settings; another shortcut may be
  using it.

### No "Saved!" notification

Check **Settings → Notifications**, and that **Do Not Disturb** is off. The
buttons in the app window always work.

### The recording stopped when the screen locked

Locking the screen yourself, closing the laptop lid or switching user ends
screen sharing. The recording is saved up to that moment.

More detail: [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md).

### Still stuck?

Open an issue on GitHub and include:

- your Ubuntu version (`lsb_release -d`) and session type (`echo $XDG_SESSION_TYPE`)
- what you did and what happened
- the messages shown when you start the app with `screen-recorder` in a terminal

---

## For developers

### How it works

- **Python 3 + GTK 4 / libadwaita** for the window (native to GNOME,
  already part of Ubuntu)
- **GStreamer** does the recording. On Wayland the screen comes from the
  **xdg-desktop-portal ScreenCast** API through PipeWire; on X11 it is
  captured with `ximagesrc`.
- **Audio** comes from PipeWire/PulseAudio sources; system audio is the output
  device's `.monitor`. Microphone and system audio are mixed with `audiomixer`.
- **Encoder:** VA-API or NVENC when they work, otherwise x264 (`veryfast`).
  No B-frames, so the video cannot appear later than the audio in the MP4.
- **Fragmented MP4** written directly: crash-safe, with no conversion step
  when you press Stop.
- **Sync over hours:** one monotonic clock for everything; sound-card drift
  is corrected by `pulsesrc`; `pacer.py` repeats the newest screen frame to
  keep a steady frame rate (`pipewiresrc`'s own `keepalive-time` freezes the
  stream on PipeWire 1.0).

### Project layout

```
screen_recorder/     the application
  app.py               start-up, command line (--toggle), notifications
  window.py            main window and settings dialog
  recorder.py          GStreamer pipeline, pause, stop, disk guard
  pacer.py             steady frame rate from screen frames
  portal.py            Wayland screen-sharing permission
  encoders.py          picks the video encoder, checks components
  audio.py             microphones and outputs
  disk.py              free space and size estimates
  hotkey.py            GNOME global shortcut
  config.py            settings file
data/                menu entry and icon
packaging/           .deb build script, package description, launcher
tests/               automated tests
docs/                TESTING.md (checklists), TROUBLESHOOTING.md
install.sh           build and install the package
uninstall.sh         remove it
run.sh               run from source
requirements.txt     Ubuntu packages needed
```

### Run from source

```bash
./run.sh
```

Command-line options: `--toggle` (start or stop recording in the running app),
`--version`, `--remove-hotkey`.

### Build the package only

```bash
./packaging/build-deb.sh
```

The result is in `dist/`.

### Tests

The tests use your real microphone and speakers, and a test picture instead
of your screen, so no dialog appears. They need `ffmpeg`, `gstreamer1.0-tools`
and `pipewire-bin`.

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

Manual checklists (1 minute, 10 minutes, 4 hours) are in
[docs/TESTING.md](docs/TESTING.md).

### Contributing

Bug reports and pull requests are welcome. Please run the tests above before
sending a change, and keep the app simple: recording the screen and audio to
MP4, reliably.

---

## License

No license has been chosen yet. Until a `LICENSE` file is added, others may
not legally reuse or redistribute this code.
