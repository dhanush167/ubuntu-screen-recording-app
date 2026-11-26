# Troubleshooting (Wayland / PipeWire)

Start the app from a terminal to see detailed error messages:

```bash
screen-recorder
```

## "Screen capture is not available" or no screen dialog appears

```bash
sudo apt install xdg-desktop-portal xdg-desktop-portal-gnome gstreamer1.0-pipewire pipewire
```

```bash
systemctl --user restart pipewire wireplumber xdg-desktop-portal-gnome xdg-desktop-portal
```

If it still fails, log out and back in. On desktops other than GNOME, install
that desktop's portal (for example `xdg-desktop-portal-kde` or `-wlr`).

## It never asks which screen to record, or records the wrong one

The choice is remembered. Press **Choose…** next to Screen, pick the monitor
and press **Share**; the Screen row then names the monitor that will be
recorded. If "Remember this selection" is switched off in the dialog, you are
asked at every Start.

## "No picture arrived from the screen"

Press **Choose…** and pick the screen again. Check that `echo $XDG_SESSION_TYPE` matches
your session. On NVIDIA proprietary drivers under Wayland, update the driver or
choose "Ubuntu on Xorg" at the login screen (where available).

## Recording stops when the screen locks

The app blocks automatic locking and sleep while recording. Locking by hand,
closing the lid or switching user ends GNOME's screen sharing; the recording is
saved up to that moment.

## Stopping from the top bar

The orange screen-sharing indicator can end sharing. The recorder then saves the
file, the same as pressing **Stop**.

## No system audio in the file

- The "Default" entry records whatever output is the default when recording starts.
- Pick the exact output (speakers, headphones, HDMI) in the drop-down instead.
- Check devices with `wpctl status`, and make sure the app that plays sound uses
  that output (Settings → Sound).

## No microphone, or silent microphone

- "No microphone found": connect one, or untick Microphone.
- Check Settings → Sound → Input: correct device, not muted, level above zero.
- If a chosen device is not present, the app falls back to "Default". If a device
  is unplugged during a recording, PipeWire normally moves the recording to
  another device without an error — watch the level bar.

## Echo: the computer sound is heard twice

The microphone picks up the speakers. Use headphones.

## Hardware encoder not used

Settings shows the encoder in use. For VA-API (Intel/AMD):

```bash
sudo apt install gstreamer1.0-plugins-bad gstreamer1.0-vaapi vainfo intel-media-va-driver mesa-va-drivers
```

```bash
vainfo
```

Look for an `H264 ... Enc` entry, then clear GStreamer's cache and restart the app:

```bash
rm -r ~/.cache/gstreamer-1.0
```

The app test-encodes a few frames with each encoder and silently uses the next
one if it fails, ending with software x264.

If hardware-encoded files look wrong, remove `gstreamer1.0-vaapi` to force x264.

## Choppy video or high CPU

Lower the frame rate to 15 or 24, or the quality to Low. When the encoder cannot
keep up, frames are dropped; audio and sync are not affected.

## The global hotkey does nothing

- Settings → Keyboard → View and Customise Shortcuts → Custom Shortcuts should
  list "Screen Recorder: start/stop".
- Choose a combination no other shortcut uses, in the app's settings.
- Only GNOME is supported. Elsewhere, bind `screen-recorder --toggle` yourself.

## No "Saved!" notification

Check Settings → Notifications and Do Not Disturb. Notifications need the
installed package; when started with `run.sh`, use the buttons in the window.

## Recovering after a crash or power cut

The MP4 is written in one-second fragments, so it plays as it is; only the last
few seconds are missing. If a player has trouble seeking in it, rewrite the index
without re-encoding:

```bash
ffmpeg -i broken.mp4 -c copy fixed.mp4
```

## X11 sessions

The screen is chosen from the drop-down and captured with `ximagesrc`. If you
change monitor layout, restart the app.
