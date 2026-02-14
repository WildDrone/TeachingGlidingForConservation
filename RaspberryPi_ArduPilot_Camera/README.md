# KU EasyGlider – MAVLink RC8 Camera Trigger (Raspberry Pi)

## Overview

This repository contains a Python script that allows a Raspberry Pi to:

- Connect to an ArduPilot flight controller via MAVLink (UART)
- Monitor **RC channel 8**
- Start image capture when **RC8 > 1700**
- Stop image capture when **RC8 < 1300**
- Automatically create timestamped session folders
- Save images in ordered sequence
- Automatically stop capture if MAVLink communication is lost

Script:

```
camera_trigger_rc8.py
```

---

## System Architecture

```
RC → ArduPilot → MAVLink (Telem2 / SERIAL5) → Raspberry Pi → Camera → Storage
```

---

## Hardware Requirements

- Pixhawk 6C (ArduPilot Plane firmware)
- Raspberry Pi (tested on Zero 2 W)
- Raspberry Pi Camera (IMX219 tested)
- UART wiring between FC and Pi

### UART Wiring

| Pixhawk | Raspberry Pi |
|----------|--------------|
| TX       | GPIO15 (RX)  |
| RX       | GPIO14 (TX)  |
| GND      | GND          |

Baud rate: **115200**

---

## Raspberry Pi Setup

### 1) OS and Serial UART

Install Raspberry Pi OS (Lite or Desktop).

Enable serial hardware:

```bash
sudo raspi-config
```

Interface Options → Serial:

- Login shell over serial: **No**
- Serial port hardware: **Yes**

Reboot.

---

### 2) Install required packages

```bash
sudo apt update
sudo apt install -y python3-venv rpicam-apps
```

---

### 3) Create Python virtual environment

```bash
mkdir -p ~/venvs
python3 -m venv ~/venvs/mav
source ~/venvs/mav/bin/activate
pip install pymavlink pyserial
```

---

### 4) Place the script

Copy:

```
camera_trigger_rc8.py
```

to:

```
/home/wilddrone/
```

Make executable:

```bash
chmod +x /home/wilddrone/camera_trigger_rc8.py
```

---

## Script Configuration (from code)

Key parameters inside the script:

```python
SERIAL_PORT = "/dev/serial0"
BAUDRATE = 115200

RC_CHANNEL = 8
RC_ON = 1700
RC_OFF = 1300

FPS = 2
WIDTH = 1920
HEIGHT = 1080
JPEG_QUALITY = 90
```

Capture runs continuously using `rpicam-still` (timelapse mode). Images are written using a numbered pattern:

```
img_000001.jpg
img_000002.jpg
...
```

Safety behaviour:

- If MAVLink is silent for more than 5 seconds, capture is stopped.

---

## Running the Script Manually

```bash
source ~/venvs/mav/bin/activate
python /home/wilddrone/camera_trigger_rc8.py
```

Expected output:

```
Connecting MAVLink on /dev/serial0 @ 115200...
MAVLink connected.
```

Flip RC8:

- **RC8 > 1700** → capture starts
- **RC8 < 1300** → capture stops

---

## Auto-Start on Boot

Create a systemd service:

```bash
sudo nano /etc/systemd/system/ku-camera.service
```

Paste:

```ini
[Unit]
Description=KU MAVLink Camera Trigger
After=network.target

[Service]
User=wilddrone
WorkingDirectory=/home/wilddrone
ExecStart=/home/wilddrone/venvs/mav/bin/python /home/wilddrone/camera_trigger_rc8.py
Restart=always
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
```

Enable and start:

```bash
sudo systemctl daemon-reload
sudo systemctl enable ku-camera.service
sudo systemctl start ku-camera.service
```

Check status:

```bash
sudo systemctl status ku-camera.service
```

---

## Flight Controller Setup (ArduPilot – Mission Planner)

This assumes the Raspberry Pi is connected to **Telem 2** on Pixhawk 6C.

Telem 2 corresponds to:

```
SERIAL5
```

In Mission Planner:

**Config → Full Parameter List**

Set:

```
SERIAL5_PROTOCOL = 2
SERIAL5_BAUD     = 115
BRD_SER2_RTSCTS  = 0
```

Write parameters and reboot the flight controller.

---

## RC Channel Setup

Assign a switch to:

```
RC8
```

Verify in Mission Planner:

**Config → Radio Calibration**

Typical ranges:

- OFF ≈ 1000–1200
- ON  ≈ 1800–2000

Script thresholds:

- ON when **RC8 > 1700**
- OFF when **RC8 < 1300**

---

## Verification Procedure

1. Power flight controller  
2. Power Raspberry Pi  
3. Confirm MAVLink connection in script output  
4. Flip RC8 ON → capture starts  
5. Flip RC8 OFF → capture stops  
6. Inspect the latest session folder for images  
