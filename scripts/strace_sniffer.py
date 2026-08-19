#!/usr/bin/env python3
"""strace-based sniffer for belt tensioner serial traffic.

Attaches strace to the running SimHub process and intercepts write()
calls on the serial port fd. No COM port hijacking — SimHub works
normally with the real Arduino.

Usage:
    python3.12 scripts/strace_sniffer.py [--pid 1277308]
    python3.12 scripts/strace_sniffer.py --analyze logs/belt_strace_<ts>.csv

The sniffer auto-detects SimHub's PID and the serial fd by scanning
/proc/<pid>/fd for /dev/ttyUSB*.
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

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from serial_proxy import ProtocolDecoder, analyze_log

# strace line: [pid XXXX] write(57, "\08\0f", 2) = 2
# We need to extract: the data bytes and decode them
# strace escapes: \NN = octal, \t \n \r \\ \" etc.
STRACE_WRITE_RE = re.compile(
    r'(?:\[pid\s+\d+\]\s+)?write\((\d+),\s+"(.*)",\s+\d+\)'
)


def find_simhub_pid() -> tuple[int, int] | None:
    """Find SimHub PID and serial fd by scanning /proc/*/fd."""
    for pid_dir in os.listdir("/proc"):
        if not pid_dir.isdigit():
            continue
        pid = int(pid_dir)
        try:
            comm = open(f"/proc/{pid}/comm").read().strip()
        except (OSError, IOError):
            continue
        if "SimHub" not in comm:
            continue
        # Found SimHub — find serial fd
        try:
            for fd_name in os.listdir(f"/proc/{pid}/fd"):
                if not fd_name.isdigit():
                    continue
                fd_path = os.readlink(f"/proc/{pid}/fd/{fd_name}")
                if "/dev/ttyUSB" in fd_path:
                    return (pid, int(fd_name))
        except (OSError, IOError):
            continue
    return None


def unescape_strace_data(s: str) -> bytes:
    r"""Convert strace-escaped string to raw bytes.

    strace uses octal escapes: \NNN (1-3 octal digits)
    Plus standard: \t \n \r \\ \" \a \b \f \v
    """
    result = bytearray()
    i = 0
    while i < len(s):
        if s[i] == '\\':
            # Try octal escape (1-3 digits)
            octal = ""
            for j in range(1, 4):
                if i + j < len(s) and s[i + j] in '01234567':
                    octal += s[i + j]
                else:
                    break
            if octal:
                result.append(int(octal, 8))
                i += 1 + len(octal)
            elif i + 1 < len(s):
                c = s[i + 1]
                escapes = {'t': 9, 'n': 10, 'r': 13, '\\': 92,
                           '"': 34, 'a': 7, 'b': 8, 'f': 12, 'v': 11}
                if c in escapes:
                    result.append(escapes[c])
                else:
                    result.append(ord(c))
                i += 2
            else:
                i += 1
        else:
            result.append(ord(s[i]))
            i += 1
    return bytes(result)


def run_sniffer(pid: int, fd: int, log_dir: Path):
    """Run the strace-based sniffer."""
    log_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = log_dir / f"belt_strace_{ts}.csv"

    print(f"\n{'='*60}")
    print(f"  Belt Tensioner strace Sniffer (passive)")
    print(f"{'='*60}")
    print(f"  SimHub PID: {pid}")
    print(f"  Serial fd:  {fd} (/dev/ttyUSB*)")
    print(f"  Log file:   {log_path}")
    print(f"{'='*60}")
    print(f"\n  → SimHub is connected. Drive!")
    print(f"  → Press Ctrl-C to stop.\n")

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

    # Start strace: trace only write() on the specific fd, follow forks
    # -e trace=write — only write syscalls
    # -f — follow child threads (SimHub uses thread pool)
    # -s 256 — capture up to 256 bytes per write
    # -xx — hex escape (cleaner than octal for parsing)
    proc = subprocess.Popen(
        ["strace", "-p", str(pid), "-e", "trace=write", "-f", "-s", "256",
         "-xx", "-o", "|cat"],  # -o pipe doesn't work, use stdout
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    # Actually strace writes to stderr, not stdout. Let's fix:
    # Restart with stderr=stdout
    proc.kill()
    proc.wait()
    proc = subprocess.Popen(
        ["strace", "-p", str(pid), "-e", "trace=write", "-f", "-s", "256",
         "-xx"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,  # line buffered
    )

    byte_count = 0

    try:
        while running[0]:
            line = proc.stdout.readline()
            if not line:
                if proc.poll() is not None:
                    break
                continue

            line = line.strip()

            # Parse strace write line
            m = STRACE_WRITE_RE.search(line)
            if not m:
                continue

            write_fd = int(m.group(1))
            if write_fd != fd:
                continue

            # Unescape the data
            data = unescape_strace_data(m.group(2))
            if not data:
                continue

            # Decode protocol
            events = decoder.feed(data)
            batch_t = time.monotonic()
            for i, (b, evt) in enumerate(zip(data, events)):
                elapsed = batch_t - t0 + i * 0.001
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
                if evt["type"] in ("position", "left_offset",
                                   "right_offset"):
                    print(f"[{elapsed:7.3f}] S→A {evt['desc']}")
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
        print(f"  Analyze: python3.12 scripts/strace_sniffer.py"
              f" --analyze {log_path}")
        print(f"{'='*60}")


def main():
    parser = argparse.ArgumentParser(
        description="strace-based sniffer for belt tensioner (passive).")
    parser.add_argument("--pid", type=int, default=None,
                        help="SimHub PID (auto-detected if omitted)")
    parser.add_argument("--fd", type=int, default=None,
                        help="Serial port fd number (auto-detected if omitted)")
    parser.add_argument("--log-dir", type=Path,
                        default=Path("logs"),
                        help="Directory for log files")
    parser.add_argument("--analyze", type=Path, metavar="CSV",
                        help="Analyze a log file instead of running sniffer")
    args = parser.parse_args()

    if args.analyze:
        analyze_log(args.analyze)
    else:
        pid = args.pid
        fd = args.fd
        if pid is None or fd is None:
            result = find_simhub_pid()
            if result is None:
                sys.exit("SimHub process not found. Is SimHub running?")
            pid, fd = result
            print(f"Auto-detected: SimHub PID={pid}, serial fd={fd}")
        run_sniffer(pid, fd, args.log_dir)


if __name__ == "__main__":
    main()