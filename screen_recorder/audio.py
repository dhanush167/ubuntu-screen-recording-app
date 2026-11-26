"""Microphones and system-audio (monitor) sources from PipeWire / PulseAudio."""

from dataclasses import dataclass

from gi.repository import Gst

# Names understood by both pipewire-pulse and PulseAudio. Using them means the
# recording follows whatever the desktop's default device is.
DEFAULT_MIC = "@DEFAULT_SOURCE@"
DEFAULT_MONITOR = "@DEFAULT_MONITOR@"


@dataclass(frozen=True)
class Device:
    id: str        # PulseAudio source name
    label: str


def _property(device, name):
    structure = device.get_properties()
    if structure is None or not structure.has_field(name):
        return None
    return structure.get_value(name)


def list_devices():
    """Return (microphones, system_audio_sources), each starting with "Default".

    A list is empty when the system has no such device.
    """
    monitor = Gst.DeviceMonitor()
    monitor.add_filter("Audio/Source", None)
    monitor.add_filter("Audio/Sink", None)
    monitor.start()
    found = monitor.get_devices() or []
    monitor.stop()

    mics, outputs = [], []
    for device in found:
        name = _property(device, "node.name")
        if not name:  # plain PulseAudio device provider
            element = device.create_element(None)
            if element is not None and element.find_property("device"):
                name = element.get_property("device")
        if not name:
            continue
        priority = int(_property(device, "priority.session") or 0)
        label = device.get_display_name()
        if device.get_device_class() == "Audio/Source":
            if _property(device, "device.class") != "monitor" and not name.endswith(".monitor"):
                mics.append((priority, Device(name, label)))
        else:
            outputs.append((priority, Device(f"{name}.monitor", label)))

    def ordered(items, default_id):
        unique = {}
        for _, device in sorted(items, key=lambda item: -item[0]):
            unique.setdefault(device.id, device)
        if not unique:
            return []
        return [Device(default_id, "Default")] + list(unique.values())

    return ordered(mics, DEFAULT_MIC), ordered(outputs, DEFAULT_MONITOR)
