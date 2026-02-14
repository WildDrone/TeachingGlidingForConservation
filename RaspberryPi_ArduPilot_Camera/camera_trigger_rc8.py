#!/usr/bin/env python3
from __future__ import annotations

import os
import time
import signal
import subprocess
from pathlib import Path
from typing import Optional

from pymavlink import mavutil

# =========================
# User configuration
# =========================
SERIAL_PORT = "/dev/serial0"
BAUDRATE = 115200

RC_CHANNEL = 8          # RC channel to monitor (1..16)
RC_ON = 1700            # switch ON threshold
RC_OFF = 1300           # switch OFF threshold (hysteresis)

BASE_DIR = Path("/home/wilddrone/recordings")  # base output directory
SESSION_PREFIX = "rc8ON"

# Camera capture settings
FPS = 2                 # change this any time (e.g., 1, 2, 5)
WIDTH = 1920            # set None to omit
HEIGHT = 1080           # set None to omit
JPEG_QUALITY = 90       # 1..100

# MAVLink stream safety
MAVLINK_SILENCE_TIMEOUT_S = 5.0


# =========================
# Internal state
# =========================
recording = False
proc: Optional[subprocess.Popen] = None
session_dir: Optional[Path] = None
last_msg_time = time.time()


def log(msg: str) -> None:
    print(msg, flush=True)


def _rc_value_from_msg(msg, ch: int) -> Optional[int]:
    # RC_CHANNELS has fields chan1_raw .. chan16_raw
    field = f"chan{ch}_raw"
    return getattr(msg, field, None)


def _next_session_index(base: Path) -> int:
    # Creates a monotonically increasing session counter based on existing folders
    # Pattern contains "__sessNNN__"
    max_n = 0
    if not base.exists():
        return 1
    for p in base.iterdir():
        if not p.is_dir():
            continue
        name = p.name
        if "__sess" in name and "__" in name:
            try:
                part = name.split("__sess", 1)[1]
                n_str = part.split("__", 1)[0]
                n = int(n_str)
                max_n = max(max_n, n)
            except Exception:
                continue
    return max_n + 1

def send_status_text(mav, text, severity=6):
    """
    severity:
    0 = EMERGENCY
    1 = ALERT
    2 = CRITICAL
    3 = ERROR
    4 = WARNING
    5 = NOTICE
    6 = INFO
    7 = DEBUG
    """
    mav.mav.statustext_send(
        severity,
        text.encode("utf-8")
    )

def play_tune(mav, tune):
    mav.mav.play_tune_send(
        mav.target_system,
        mav.target_component,
        tune.encode("utf-8"),
        b""
    )

def start_capture() -> None:
    global recording, proc, session_dir

    BASE_DIR.mkdir(parents=True, exist_ok=True)

    ts = time.strftime("%Y%m%d_%H%M%S")
    sess_n = _next_session_index(BASE_DIR)
    session_name = f"{ts}__sess{sess_n:03d}__{SESSION_PREFIX}"
    session_dir = BASE_DIR / session_name
    session_dir.mkdir(parents=True, exist_ok=True)

    # Metadata file
    meta = session_dir / "meta.txt"
    meta.write_text(
        "\n".join([
            f"session_name: {session_name}",
            f"started_utc: {time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime())}",
            f"rc_channel: {RC_CHANNEL}",
            f"rc_on_threshold: {RC_ON}",
            f"rc_off_threshold: {RC_OFF}",
            f"fps: {FPS}",
            f"width: {WIDTH}",
            f"height: {HEIGHT}",
            f"jpeg_quality: {JPEG_QUALITY}",
        ]) + "\n"
    )

    # rpicam-jpeg continuous capture:
    # -t 0 : run until stopped
    # --timelapse ms : periodic capture
    # -o pattern : supports printf-style numbering (%06d)
    # Use a pattern that keeps ordering + human time hint
    # (timestamp in filename is approximate; numbering is the true order)
    timelapse_ms = max(1, int(1000 / max(0.1, FPS)))

    out_pattern = str(session_dir / "img_%06d.jpg")

    cmd = [
        "rpicam-still",
        "-t", "0",
        "--timelapse", str(timelapse_ms),
        "--output", out_pattern,
        "--quality", str(JPEG_QUALITY),
        "--nopreview",
    ]

    if WIDTH is not None:
        cmd += ["--width", str(WIDTH)]
    if HEIGHT is not None:
        cmd += ["--height", str(HEIGHT)]

    proc = subprocess.Popen(cmd)
    recording = True
    send_status_text(mav, "RPi CAPTURE STARTED", 5)
    play_tune(mav, "MFT200L8>c")
    log(f"CAPTURE STARTED → {session_dir}")


def stop_capture() -> None:
    global recording, proc, session_dir

    if proc and proc.poll() is None:
        proc.send_signal(signal.SIGTERM)
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5)

    proc = None
    recording = False
    send_status_text(mav, "RPi CAPTURE STOPPED", 5)
    play_tune(mav, "MFT200L8>cc")
    if session_dir:
        log(f"CAPTURE STOPPED → {session_dir}")
    session_dir = None


def main() -> int:
    global last_msg_time

    log(f"Connecting MAVLink on {SERIAL_PORT} @ {BAUDRATE}...")
    mav = mavutil.mavlink_connection(SERIAL_PORT, baud=BAUDRATE)

    while True:
        try:
            hb = mav.wait_heartbeat(timeout=10)
            print("MAVLink connected.")
            break
        except Exception as e:
            print(f"MAVLink not ready yet ({e}). Retrying in 5s...")
            time.sleep(5)

    if not hb:
        log("ERROR: No heartbeat. Check FC SERIAL port settings and wiring.")
        return 1

    log("MAVLink connected.")
    last_msg_time = time.time()

    try:
        while True:
            msg = mav.recv_match(blocking=True, timeout=1)
            now = time.time()

            # If MAVLink goes quiet, stop capture for safety
            if (now - last_msg_time) > MAVLINK_SILENCE_TIMEOUT_S:
                if recording:
                    log("MAVLink timeout → stopping capture for safety")
                    stop_capture()
                continue

            if msg is None:
                continue

            last_msg_time = now

            if msg.get_type() != "RC_CHANNELS":
                continue

            rc_val = _rc_value_from_msg(msg, RC_CHANNEL)
            if rc_val is None:
                continue

            # Start when ON
            if (rc_val > RC_ON) and (not recording):
                start_capture()

            # Stop when OFF
            elif (rc_val < RC_OFF) and recording:
                stop_capture()

    except KeyboardInterrupt:
        log("Interrupted.")
    finally:
        stop_capture()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
