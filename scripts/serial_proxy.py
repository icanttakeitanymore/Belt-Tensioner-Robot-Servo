#!/usr/bin/env python3
"""Serial proxy for sniffing SimHub ↔ Arduino belt tensioner traffic.

Creates a PTY pair: SimHub connects to the slave end (symlinked as COM port in
Wine), the master end is read/written by this proxy. Data is forwarded to the
real Arduino on /dev/ttyUSB* and every byte is logged + decoded.

Usage:
    python3.12 scripts/serial_proxy.py [--arduino /dev/ttyUSB1] [--baud 9600]
    python3.12 scripts/serial_proxy.py --analyze logfile.csv

Setup:
    1. Stop SimHub (or disable the Custom Serial Device)
    2. Run this proxy — it prints the PTY slave path (e.g. /dev/pts/3)
    3. Repoint Wine COM3 to the PTY slave:
       ln -sf /dev/pts/3 ~/.wine/dosdevices/com3
    4. Re-enable the SimHub Custom Serial Device
    5. Drive! Press Ctrl-C to stop. Log saved to logs/belt_log_<timestamp>.csv
    6. Analyze: python3.12 scripts/serial_proxy.py --analyze logs/belt_log_*.csv
"""

import argparse
import csv
import os
import select
import signal
import sys
import time
from datetime import datetime
from pathlib import Path

try:
    import serial
except ImportError:
    sys.exit("pyserial required: pip install pyserial (use python3.12)")

# ── Protocol decode ────────────────────────────────────────────────

OPCODE_LEFT_OFFSET = 0
OPCODE_RIGHT_OFFSET = 1

# Parser state machine (mirrors Arduino firmware)
STATE_NORMAL = 0
STATE_EXPECTING_LEFT_OFFSET = 1
STATE_EXPECTING_RIGHT_OFFSET = 2


class ProtocolDecoder:
    """Stateful decoder — mirrors the Arduino parser state machine."""

    def __init__(self, label: str):
        self.label = label
        self.state = STATE_NORMAL
        self.ladd = 0
        self.radd = 0

    def feed(self, data: bytes) -> list[dict]:
        """Feed raw bytes, return list of decoded events."""
        events = []
        for b in data:
            if self.state == STATE_EXPECTING_LEFT_OFFSET:
                self.ladd = b
                self.state = STATE_NORMAL
                events.append({
                    "type": "left_offset",
                    "raw": b,
                    "offset": b,
                    "desc": f"Left offset calibration = {b}°",
                })
            elif self.state == STATE_EXPECTING_RIGHT_OFFSET:
                self.radd = b
                self.state = STATE_NORMAL
                events.append({
                    "type": "right_offset",
                    "raw": b,
                    "offset": b,
                    "desc": f"Right offset calibration = {b}°",
                })
            else:
                if b == OPCODE_LEFT_OFFSET:
                    self.state = STATE_EXPECTING_LEFT_OFFSET
                    events.append({
                        "type": "opcode",
                        "raw": b,
                        "desc": "Opcode 0: expect left offset next",
                    })
                elif b == OPCODE_RIGHT_OFFSET:
                    self.state = STATE_EXPECTING_RIGHT_OFFSET
                    events.append({
                        "type": "opcode",
                        "raw": b,
                        "desc": "Opcode 1: expect right offset next",
                    })
                else:
                    # Position command: LSB = channel, bits 1-6 = angle
                    channel = "right" if (b & 1) else "left"
                    angle = b & 127
                    servo_angle = angle  # before offset
                    final_angle = angle + (self.radd if channel == "right" else self.ladd)
                    events.append({
                        "type": "position",
                        "raw": b,
                        "channel": channel,
                        "angle_7bit": angle,
                        "offset": self.radd if channel == "right" else self.ladd,
                        "final_angle": final_angle,
                        "desc": f"{channel.upper()} servo: raw={angle}° + offset={self.radd if channel == 'right' else self.ladd}° → {final_angle}°",
                    })
        return events


# ── Proxy mode ─────────────────────────────────────────────────────

def run_proxy(arduino_port: str, baud: int, log_dir: Path):
    """Run the PTY proxy between SimHub and Arduino."""
    log_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = log_dir / f"belt_log_{ts}.csv"

    # Open Arduino
    try:
        arduino = serial.Serial(arduino_port, baud, timeout=0.01,
                                rtscts=False, dsrdtr=False)
    except Exception as e:
        sys.exit(f"Cannot open Arduino on {arduino_port}: {e}")

    # Create PTY pair
    master_fd, slave_fd = os.openpty()
    slave_name = os.ttyname(slave_fd)

    # Disable PTY echo — without this, data written to master (Arduino→SimHub)
    # gets echoed back to master and misread as SimHub→Arduino traffic.
    import termios
    try:
        attrs = termios.tcgetattr(slave_fd)
        attrs[3] &= ~termios.ECHO       # disable echo
        attrs[3] &= ~termios.ICANON      # raw mode (no line buffering)
        attrs[1] = 0                     # disable output processing
        termios.tcsetattr(slave_fd, termios.TCSANOW, attrs)
    except OSError:
        pass  # non-fatal — echo may still be off by default on some systems
    # Keep slave_fd open for the proxy's lifetime — on Linux, reading from
    # a PTY master whose slave is fully closed returns EIO (errno 5).

    print(f"\n{'='*60}")
    print(f"  Belt Tensioner Serial Proxy")
    print(f"{'='*60}")
    print(f"  Arduino:  {arduino_port} @ {baud} baud")
    print(f"  PTY slave: {slave_name}")
    print(f"  Log file:  {log_path}")
    print(f"{'='*60}")
    print(f"\n  → Repoint Wine COM3 to the PTY slave:")
    print(f"    ln -sf {slave_name} ~/.wine/dosdevices/com3")
    print(f"\n  → Then re-enable SimHub Custom Serial Device.")
    print(f"  → Press Ctrl-C to stop.\n")

    dec_sim2ard = ProtocolDecoder("SimHub→Arduino")
    dec_ard2sim = ProtocolDecoder("Arduino→SimHub")

    log_file = open(log_path, "w", newline="")
    writer = csv.writer(log_file)
    writer.writerow(["timestamp", "elapsed_s", "direction", "raw_byte",
                     "type", "channel", "angle_7bit", "offset", "final_angle",
                     "description"])

    t0 = time.monotonic()
    running = [True]

    def shutdown(signum, frame):
        running[0] = False
    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    # Set master_fd non-blocking
    import fcntl
    flags = fcntl.fcntl(master_fd, fcntl.F_GETFL)
    fcntl.fcntl(master_fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)

    byte_count = 0
    try:
        while running[0]:
            # Wait for data on either fd
            rlist = [master_fd, arduino.fileno()]
            try:
                readable, _, _ = select.select(rlist, [], [], 0.1)
            except (OSError, ValueError):
                break

            # SimHub → Arduino
            if master_fd in readable:
                try:
                    data = os.read(master_fd, 256)
                except BlockingIOError:
                    data = b""
                if data:
                    arduino.write(data)
                    events = dec_sim2ard.feed(data)
                    batch_t = time.monotonic()
                    # Spread timestamps across bytes in the batch so each
                    # gets a distinct time (serial at 9600 baud = ~0.96ms/byte)
                    byte_interval = 1.0 / (baud / 10.0)  # 10 bits per byte (8N1+start+stop)
                    for i, (b, evt) in enumerate(zip(data, events)):
                        elapsed = batch_t - t0 + i * byte_interval
                        ts_str = datetime.now().isoformat(timespec="milliseconds")
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
                        # Only print position + offset events (skip opcode noise)
                        if evt["type"] in ("position", "left_offset", "right_offset"):
                            print(f"[{elapsed:7.3f}] S→A {evt['desc']}")

                    log_file.flush()

            # Arduino → SimHub (boot message, etc.)
            if arduino.fileno() in readable:
                try:
                    data = arduino.read(256)
                except Exception:
                    data = b""
                if data:
                    try:
                        os.write(master_fd, data)
                        # Drain any echo from master immediately — even with
                        # termios ECHO off, some PTY drivers still echo.
                        select.select([master_fd], [], [], 0.01)
                        try:
                            while True:
                                echo = os.read(master_fd, 256)
                                if not echo:
                                    break
                        except (BlockingIOError, OSError):
                            pass
                    except OSError:
                        pass
                    now = time.monotonic()
                    elapsed = now - t0
                    text = data.decode("ascii", errors="replace").strip()
                    if text:
                        print(f"[{elapsed:7.3f}] A→S {repr(text)}")
                        ts_str = datetime.now().isoformat(timespec="milliseconds")
                        writer.writerow([
                            ts_str, f"{elapsed:.4f}", "A→S",
                            "", "arduino_msg", "", "", "", "",
                            f"Arduino: {text}",
                        ])
                        log_file.flush()
    finally:
        log_file.close()
        os.close(slave_fd)
        os.close(master_fd)
        arduino.close()
        print(f"\n{'='*60}")
        print(f"  Proxy stopped. {byte_count} bytes logged.")
        print(f"  Log: {log_path}")
        print(f"  Analyze: python3.12 scripts/serial_proxy.py --analyze {log_path}")
        print(f"{'='*60}")


# ── Analysis mode ───────────────────────────────────────────────────

def analyze_log(log_path: Path):
    """Analyze a logged CSV and print summary stats."""
    if not log_path.exists():
        sys.exit(f"Log not found: {log_path}")

    rows = []
    with open(log_path, newline="") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    if not rows:
        sys.exit("Log is empty!")

    print(f"\n{'='*60}")
    print(f"  Belt Tensioner Log Analysis: {log_path.name}")
    print(f"{'='*60}")
    print(f"  Total rows: {len(rows)}")

    # Parse numeric fields
    s2a = [r for r in rows if r["direction"] == "S→A"]
    a2s = [r for r in rows if r["direction"] == "A→S"]

    positions = []
    offsets = []
    for r in s2a:
        if r["type"] == "position":
            try:
                positions.append({
                    "t": float(r["elapsed_s"]),
                    "channel": r["channel"],
                    "angle": int(r["angle_7bit"]),
                    "offset": int(r["offset"]) if r["offset"] else 0,
                    "final": int(r["final_angle"]) if r["final_angle"] else 0,
                })
            except (ValueError, KeyError):
                pass
        elif r["type"] in ("left_offset", "right_offset"):
            try:
                offsets.append({
                    "t": float(r["elapsed_s"]),
                    "type": r["type"],
                    "value": int(r["offset"]),
                })
            except (ValueError, KeyError):
                pass

    if not positions:
        print("  No position commands logged!")
        return

    # Time range
    t_min = positions[0]["t"]
    t_max = positions[-1]["t"]
    duration = max(t_max - t_min, 0.001)  # clamp to avoid div-by-zero
    print(f"  Duration: {duration:.1f}s ({t_min:.2f} – {t_max:.2f})")
    print(f"  Position commands: {len(positions)} ({len(positions)/duration:.1f}/s avg)")
    print(f"  Offset commands: {len(offsets)}")
    print(f"  Arduino messages: {len(a2s)}")

    # Per-channel stats
    for ch in ("left", "right"):
        ch_pos = [p for p in positions if p["channel"] == ch]
        if not ch_pos:
            continue
        angles = [p["angle"] for p in ch_pos]
        finals = [p["final"] for p in ch_pos]
        print(f"\n  {ch.upper()} channel ({len(ch_pos)} commands):")
        print(f"    Raw 7-bit angle:  min={min(angles)}  max={max(angles)}  mean={sum(angles)/len(angles):.1f}")
        print(f"    Final (w/offset): min={min(finals)}  max={max(finals)}  mean={sum(finals)/len(finals):.1f}")

        # Distribution histogram (10 bins)
        bins = [0] * 10
        for a in angles:
            idx = min(int(a / 12.8), 9)
            bins[idx] += 1
        bar_max = max(bins) if bins else 1
        print(f"    Distribution (raw angle, 0-127):")
        for i, count in enumerate(bins):
            bar_len = int(count / bar_max * 40) if bar_max else 0
            label = f"{i*13:3d}-{(i+1)*13-1:3d}"
            print(f"      {label}: {'█'*bar_len} {count}")

    # Event timeline (gear kicks, offset changes)
    print(f"\n  Offset calibration events:")
    for o in offsets:
        print(f"    [{o['t']:7.3f}] {o['type']}: {o['value']}°")

    # Detect rapid changes (potential kick events)
    kick_threshold = 20  # angle jump > 20 in one step
    kicks = []
    prev = {}
    for p in positions:
        ch = p["channel"]
        if ch in prev:
            delta = p["angle"] - prev[ch]["angle"]
            if abs(delta) > kick_threshold:
                kicks.append({
                    "t": p["t"],
                    "channel": ch,
                    "from": prev[ch]["angle"],
                    "to": p["angle"],
                    "delta": delta,
                })
        prev[ch] = p

    if kicks:
        print(f"\n  Transient events (|Δ| > {kick_threshold}): {len(kicks)}")
        for k in kicks[:30]:
            direction = "↑" if k["delta"] > 0 else "↓"
            print(f"    [{k['t']:7.3f}] {k['channel'].upper():5s} {k['from']:3d}→{k['to']:3d} ({direction}{abs(k['delta'])})")
        if len(kicks) > 30:
            print(f"    ... and {len(kicks)-30} more")
    else:
        print(f"\n  No transient events detected (threshold={kick_threshold})")

    print(f"\n{'='*60}\n")


def main():
    parser = argparse.ArgumentParser(
        description="Serial proxy + logger for belt tensioner.")
    parser.add_argument("--arduino", default="/dev/ttyUSB1",
                        help="Arduino serial port (default: /dev/ttyUSB1)")
    parser.add_argument("--baud", type=int, default=9600,
                        help="Baud rate (default: 9600)")
    parser.add_argument("--log-dir", type=Path,
                        default=Path("logs"),
                        help="Directory for log files")
    parser.add_argument("--analyze", type=Path, metavar="CSV",
                        help="Analyze a log file instead of running proxy")
    args = parser.parse_args()

    if args.analyze:
        analyze_log(args.analyze)
    else:
        run_proxy(args.arduino, args.baud, args.log_dir)


if __name__ == "__main__":
    main()