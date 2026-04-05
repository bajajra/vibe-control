"""
Native DualSense rumble via macOS IOKit — works over both USB and Bluetooth.

pygame/SDL's rumble() silently fails for DualSense over Bluetooth on macOS.
This module uses IOHIDDeviceSetReport (via ctypes) to send HID output reports
directly.  IOHIDManager shares the device with SDL — no exclusive claim, no
stolen input events.

Bluetooth output reports (0x31) require a CRC32 checksum; USB reports (0x02)
do not.  Connection type is detected from the SDL joystick GUID (bus byte).
"""

import ctypes
from ctypes import c_void_p, c_int32, c_uint32, c_uint8, c_long, byref, POINTER
import sys
import zlib

VENDOR_ID = 0x054C   # Sony
PRODUCT_ID = 0x0CE6  # DualSense

_BT_OUTPUT_PREFIX = 0xA2
_kIOHIDReportTypeOutput = 1


def _load_iokit():
    """Load IOKit and CoreFoundation, define function signatures."""
    if sys.platform != "darwin":
        return None, None
    try:
        iokit = ctypes.CDLL("/System/Library/Frameworks/IOKit.framework/IOKit")
        cfl = ctypes.CDLL(
            "/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation"
        )
    except OSError:
        return None, None

    cfl.CFNumberCreate.restype = c_void_p
    cfl.CFNumberCreate.argtypes = [c_void_p, c_int32, c_void_p]
    cfl.CFDictionaryCreate.restype = c_void_p
    cfl.CFDictionaryCreate.argtypes = [
        c_void_p, POINTER(c_void_p), POINTER(c_void_p), c_long, c_void_p, c_void_p,
    ]
    cfl.CFStringCreateWithCString.restype = c_void_p
    cfl.CFStringCreateWithCString.argtypes = [c_void_p, ctypes.c_char_p, c_uint32]
    cfl.CFSetGetCount.restype = c_long
    cfl.CFSetGetCount.argtypes = [c_void_p]
    cfl.CFSetGetValues.argtypes = [c_void_p, POINTER(c_void_p)]
    cfl.CFRelease.argtypes = [c_void_p]

    iokit.IOHIDManagerCreate.restype = c_void_p
    iokit.IOHIDManagerCreate.argtypes = [c_void_p, c_uint32]
    iokit.IOHIDManagerSetDeviceMatching.restype = None
    iokit.IOHIDManagerSetDeviceMatching.argtypes = [c_void_p, c_void_p]
    iokit.IOHIDManagerOpen.restype = c_int32
    iokit.IOHIDManagerOpen.argtypes = [c_void_p, c_uint32]
    iokit.IOHIDManagerClose.restype = c_int32
    iokit.IOHIDManagerClose.argtypes = [c_void_p, c_uint32]
    iokit.IOHIDManagerCopyDevices.restype = c_void_p
    iokit.IOHIDManagerCopyDevices.argtypes = [c_void_p]
    iokit.IOHIDDeviceSetReport.restype = c_int32
    iokit.IOHIDDeviceSetReport.argtypes = [
        c_void_p, c_int32, c_int32, POINTER(c_uint8), c_long,
    ]

    return iokit, cfl


def _cfstr(cfl, s):
    return cfl.CFStringCreateWithCString(None, s.encode("utf-8"), 0x08000100)


def _cfint(cfl, n):
    v = c_int32(n)
    return cfl.CFNumberCreate(None, 3, byref(v))


def is_bluetooth_guid(guid: str) -> bool:
    """Check SDL joystick GUID — first byte 0x03 = Bluetooth, 0x05 = USB."""
    if not guid or len(guid) < 2:
        return False
    try:
        return int(guid[:2], 16) == 0x03
    except ValueError:
        return False


def detect_hid_bt() -> bool:
    """Detect USB vs Bluetooth by reading a HID input report.

    USB input reports: 64 bytes, report ID 0x01
    BT input reports:  78 bytes, report ID 0x31

    This is more reliable than the SDL GUID, which can be wrong on macOS
    when the controller is paired via BT but communicating over USB HID.
    """
    try:
        import hid
        dev = hid.device()
        dev.open(VENDOR_ID, PRODUCT_ID)
        dev.set_nonblocking(0)
        data = dev.read(128, timeout_ms=500)
        dev.close()
        if data and len(data) >= 70 and data[0] == 0x31:
            return True   # Bluetooth
        return False      # USB (or ambiguous)
    except Exception:
        return False


class DualSenseRumble:
    """Direct IOKit HID rumble for DualSense — coexists with SDL."""

    def __init__(self):
        self._iokit = None
        self._cf = None
        self._manager = None
        self._dev = None
        self._bt = None
        self._seq = 0

    @property
    def is_bluetooth(self):
        return self._bt is True

    @staticmethod
    def available():
        if sys.platform != "darwin":
            return False
        iokit, _ = _load_iokit()
        return iokit is not None

    def probe(self, bluetooth: bool = True):
        """Open IOHIDManager and find the DualSense.

        Args:
            bluetooth: whether the controller is connected via BT (from GUID).
                       Determines which report format to use.
        """
        self._iokit, self._cf = _load_iokit()
        if not self._iokit:
            return False
        self._bt = bluetooth
        try:
            return self._open_manager()
        except Exception:
            self._dev = None
            return False

    def _open_manager(self):
        cf = self._cf
        iokit = self._iokit

        keys = (c_void_p * 2)(_cfstr(cf, "VendorID"), _cfstr(cf, "ProductID"))
        vals = (c_void_p * 2)(_cfint(cf, VENDOR_ID), _cfint(cf, PRODUCT_ID))
        kk = c_void_p.in_dll(cf, "kCFTypeDictionaryKeyCallBacks")
        kv = c_void_p.in_dll(cf, "kCFTypeDictionaryValueCallBacks")
        match_dict = cf.CFDictionaryCreate(
            None, keys, vals, 2, ctypes.addressof(kk), ctypes.addressof(kv),
        )

        self._manager = iokit.IOHIDManagerCreate(None, 0)
        iokit.IOHIDManagerSetDeviceMatching(self._manager, match_dict)
        ret = iokit.IOHIDManagerOpen(self._manager, 0)
        if ret != 0:
            return False

        device_set = iokit.IOHIDManagerCopyDevices(self._manager)
        if not device_set:
            return False
        count = cf.CFSetGetCount(device_set)
        if count == 0:
            cf.CFRelease(device_set)
            return False

        devs = (c_void_p * count)()
        cf.CFSetGetValues(device_set, devs)
        self._dev = devs[0]
        cf.CFRelease(device_set)
        return True

    def open(self):
        """Alias for probe()."""
        return self.probe()

    def close(self):
        """Stop motors and release the IOHIDManager."""
        if self._dev:
            try:
                self.rumble(0, 0)
            except Exception:
                pass
        if self._manager and self._iokit:
            try:
                self._iokit.IOHIDManagerClose(self._manager, 0)
            except Exception:
                pass
        self._dev = None
        self._manager = None
        self._bt = None

    def rumble(self, low_freq: float, high_freq: float, duration_ms: int = 0):
        """Send rumble.  low_freq/high_freq are 0.0–1.0 (same scale as pygame).
        Returns True on success."""
        if not self._dev or not self._iokit:
            return False
        left = int(max(0.0, min(1.0, low_freq)) * 255)
        right = int(max(0.0, min(1.0, high_freq)) * 255)
        try:
            if self._bt:
                return self._send_bt(right, left)
            else:
                return self._send_usb(right, left)
        except Exception:
            return False

    def _write_report(self, report_id, data):
        buf = (c_uint8 * len(data))(*data)
        ret = self._iokit.IOHIDDeviceSetReport(
            self._dev, _kIOHIDReportTypeOutput, report_id, buf, len(data),
        )
        return ret == 0

    def _send_bt(self, right_motor, left_motor):
        report = bytearray(78)
        report[0] = 0x31
        report[1] = (self._seq << 4) | 0x02
        report[2] = 0x10
        report[3] = 0x03
        report[5] = right_motor
        report[6] = left_motor
        crc_data = bytes([_BT_OUTPUT_PREFIX]) + bytes(report[:74])
        crc = zlib.crc32(crc_data) & 0xFFFFFFFF
        report[74:78] = crc.to_bytes(4, "little")
        self._seq = (self._seq + 1) & 0x0F
        return self._write_report(0x31, report)

    def _send_usb(self, right_motor, left_motor):
        report = bytearray(48)
        report[0] = 0x02
        report[1] = 0x03
        report[3] = right_motor
        report[4] = left_motor
        return self._write_report(0x02, report)
