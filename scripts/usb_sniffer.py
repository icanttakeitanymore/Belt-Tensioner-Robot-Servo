#!/usr/bin/env python3
"""USB sniffer for belt tensioner serial traffic via usbmon.

Reads Linux kernel usbmon (debugfs) and decodes CH340 serial data for
the belt tensioner Arduino. SimHub connects to the real Arduino — this
script only listens passively, no COM port hijacking.

Setup (one-time):
    sudo modprobe usbmon
    sudo mount -t debugfs none /sys/kernel/debug
    sudo bash -c 'echo "bpolozov ALL=(root) NOPASSWD: /bin/cat /sys/kernel/debug/usb/usbmon/1t" > /etc/sudoers.d/usbmon && chmod 440 /etc/sudoers.d/usbmon'

Usage:
    python3.12 scripts/usb_sniffer.py
    python3.12 scripts/usb_sniffer.py --device 036
    python3.12 scripts/usb_sniffer.py --analyze logs/belt_usb_<ts>.csv

The sniffer auto-detects the CH340 on /dev/ttyUSB1 (bus 1, device from
sysfs). Reads usbmon via passwordless sudo, filters for that device's
bulk OUT endpoint (SimHub→Arduino data), decodes the serial protocol,
and logs to CSV.
"""

import argparse
import csv
import os
import re
import signal
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

# Reuse protocol decoder from serial_proxy
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from serial_proxy import ProtocolDecoder

# ── usbmon text format ─────────────────────────────────────────────
# Line format:
#   ffff... timestamp S/C Type:dev:ep status length = hexdata
# Type: Bo=bulk OUT, Bi=bulk IN, Ii=interrupt IN, Zo=isochronous OUT, etc.
# S = submission (URB submitted), C = completion (URB completed)
# We want C (completion) lines with data — those have the actual payload.
# For bulk OUT (Bo), the S line has the data being sent.
# For bulk IN (Bi), the C line has the received data.

USBMON_LINE_RE = re.compile(
    r'^\S+\s+(\d+)\s+'          # URB address + timestamp
    r'([SC])\s+'                 # S=submit, C=complete
    r'(\w+):(\d+):(\d+)\s+'      # type:device:endpoint
    r'(-?\d+)\s+'                # status
    r'(\d+)\s*'                  # length
    r'(?:=\s+(.*))?'             # optional hex data
)


def find_arduino_device() -> str:
    """Find USB device number for /dev/ttyUSB1 via sysfs."""
    try:
        # /dev/ttyUSB1 → /sys/bus/usb/devices/1-10/
        syspath = os.path.realpath("/sys/class/tty/ttyUSB1/device/../..")
        devnum_file = os.path.join(syspath, "devnum")
        with open(devnum_file) as f:
            return f.read().strip()
    except (OSError, IOError):
        return "036"  # fallback


def parse_usbmon_line(line: str):
    """Parse a usbmon text line, return (direction, device, endpoint, data_bytes) or None."""
    m = USBMON_LINE_RE.match(line.strip())
    if not m:
        return None

    timestamp, submit_complete, urb_type, device, endpoint, status, length, hexdata = m.groups()

    # Only care about our device
    # (filtering done by caller)

    # Only lines with hex data
    if not hexdata:
        return None

    # Parse hex data: groups of 8 hex digits (4 bytes each), space-separated
    # e.g.: "0000001e 00000041" → bytes 0x00,0x00,0x00,0x1e,0x00,0x00,0x00,0x41
    # But usbmon stores raw bytes in little-endian dword groups? No —
    # actually usbmon hex is just raw bytes shown as 32-bit words.
    # Each word is 4 bytes in byte order (NOT endian-swapped on little-endian).
    # Actually: usbmon prints data as 32-bit hex words, byte-order = native.
    # On x86 (little-endian), "44434241" = bytes 41 42 43 44 = "ABCD"
    # We need to byte-swap each 4-byte group.

    words = hexdata.split()
    raw = bytearray()
    for word in words:
        # Each word is 8 hex chars = 4 bytes, native endian (LE on x86)
        if len(word) == 8:
            val = int(word, 16)
            raw.extend(val.to_bytes(4, 'little'))
        elif len(word) == 4:
            val = int(word, 16)
            raw.extend(val.to_bytes(2, 'little'))
        else:
            # Fallback: treat as raw hex string
            raw.extend(bytes.fromhex(word))

    # Direction: Bo = bulk OUT (SimHub→Arduino), Bi = bulk IN (Arduino→SimHub)
    direction = None
    if urb_type == "Bo" and submit_complete == "S":
        direction = "S→A"
    elif urb_type == "Bi" and submit_complete == "C":
        direction = "A→S"
    elif urb_type == "Bo" and submit_complete == "C":
        # Completion of bulk OUT — no data (already in S line)
        return None
    else:
        return None

    return (direction, device, endpoint, bytes(raw))


# ── Sniffer mode ───────────────────────────────────────────────────

def run_sniffer(device: str, log_dir: Path, bus: int = 1):
    """Run the USB sniffer."""
    log_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = log_dir / f"belt_usb_{ts}.csv"

    usbmon_path = f"/sys/kernel/debug/usb/usbmon/{bus}t"

    # Check usbmon is available (via sudo, since debugfs is root-only)
    check = subprocess.run(
        ["sudo", "-n", "cat", usbmon_path],
        capture_output=True, text=True, timeout=5)
    if check.returncode != 0:
        sys.exit(f"Cannot read {usbmon_path}: {check.stderr.strip()}\n"
                 "Run: sudo modprobe usbmon && "
                 "sudo mount -t debugfs none /sys/kernel/debug\n"
                 "And set up sudoers: see scripts/usb_sniffer.py docstring")

    print(f"\n{'='*60}")
    print(f"  Belt Tensioner USB Sniffer (passive)")
    print(f"{'='*60}")
    print(f"  Bus:        {bus}")
    print(f"  Device:     {device} (CH340 on /dev/ttyUSB1)")
    print(f"  usbmon:     {usbmon_path}")
    print(f"  Log file:   {log_path}")
    print(f"{'='*60}")
    print(f"\n  → Make sure SimHub is connected to the Arduino.")
    print(f"  → Drive! Press Ctrl-C to stop.\n")

    decoder = ProtocolDecoder("SimHub→Arduino")

    log_file = open(log_path, "w", newline="")
    writer = csv.writer(log_file)
    writer.writerow(["timestamp", "elapsed_s", "direction", "raw_byte",
                     "type", "channel", "angle_7bit", "offset",
                     "final_angle", "description"])

    t0 = time.monotonic()
    running = [True]

    def shutdown(signum, frame):
        running[0] = False
    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    # Start usbmon reader via sudo
    proc = subprocess.Popen(
        ["sudo", "-n", "cat", usbmon_path],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    byte_count = 0

    try:
        while running[0]:
            line = proc.stdout.readline()
            if not line:
                # Check if process died
                if proc.poll() is not None:
                    stderr = proc.stderr.read()
                    sys.exit(f"usbmon reader died: {stderr}")
                break

            parsed = parse_usbmon_line(line)
            if parsed is None:
                continue

            direction, dev, ep, data = parsed

            # Filter: only our device
            if dev != device:
                continue

            if not data:
                continue

            if direction == "S→A":
                events = decoder.feed(data)
                batch_t = time.monotonic()
                for i, (b, evt) in enumerate(zip(data, events)):
                    elapsed = batch_t - t0 + i * 0.001
                    ts_str = datetime.now().isoformat(
                        timespec="milliseconds")
                    writer.writerow([
                        ts_str, f"{elapsed:.4f}", "S→A",
                        b, evt["type"],
                        evt.get("channel", ""),
                        evt.get("angle_7bit", ""),
                        evt.get("offset", ""),
                        evt.get("final_angle", ""),
                        evt["desc"],
                    ])
                    byte_count += 1
                    if evt["type"] in ("position", "left_offset",
                                       "right_offset"):
                        print(f"[{elapsed:7.3f}] S→A {evt['desc']}")
                log_file.flush()

            elif direction == "A→S":
                now = time.monotonic()
                elapsed = now - t0
                text = data.decode("ascii", errors="replace").strip()
                if text:
                    print(f"[{elapsed:7.3f}] A→S {repr(text)}")
                    ts_str = datetime.now().isoformat(
                        timespec="milliseconds")
                    writer.writerow([
                        ts_str, f"{elapsed:.4f}", "A→S",
                        "", "arduino_msg", "", "", "", "",
                        f"Arduino: {text}",
                    ])
                    log_file.flush()

    except KeyboardInterrupt:
        pass
    finally:
        proc.kill()
        proc.wait()
        log_file.close()
        print(f"\n{'='*60}")
        print(f"  Sniffer stopped. {byte_count} bytes logged.")
        print(f"  Log: {log_path}")
        print(f"  Analyze: python3.12 scripts/usb_sniffer.py"
              f" --analyze {log_path}")
        print(f"{'='*60}")


# ── Analysis mode (reuses serial_proxy analyzer) ────────────────────

def analyze_log(log_path: Path):
    """Analyze a logged CSV — same format as serial_proxy."""
    from serial_proxy import analyze_log as _analyze
    _analyze(log_path)


def main():
    parser = argparse.ArgumentParser(
        description="USB sniffer for belt tensioner (passive, via usbmon).")
    parser.add_argument("--device", default=None,
                        help="USB device number (auto-detected from /dev/ttyUSB1)")
    parser.add_argument("--bus", type=int, default=1,
                        help="USB bus number (default: 1)")
    parser.add_argument("--log-dir", type=Path,
                        default=Path("logs"),
                        help="Directory for log files")
    parser.add_argument("--analyze", type=Path, metavar="CSV",
                        help="Analyze a log file instead of running sniffer")
    args = parser.parse_args()

    if args.analyze:
        analyze_log(args.analyze)
    else:
        device = args.device or find_arduino_device()
        run_sniffer(device, args.log_dir, args.bus)


if __name__ == "__main__":
    main()