# Belt-Tensioner-Robot-Servo

Sim Racing Belt Tensioner using robot hobby servos and SimHub.

Based on the original project by [blekenbleu](https://github.com/blekenbleu) —
[SimHub Custom serial device for Blue Pill](https://blekenbleu.github.io/Arduino/SimHubCustomSerial).

## What it does

Two high-torque hobby servos pull your shoulder harnesses based on live telemetry
from SimHub. Braking tightens both belts; cornering tightens the outside belt.
Gear shifts, suspension bumps, and wheel lockup produce sharp transient tugs.
Handbrake and pit-limiter automatically slacken the belts.

YouTube demo: https://www.youtube.com/watch?v=9a0rFGwfBp4

## Hardware

### Bill of Materials

- Arduino Nano
- 2× DSServo RDS5160 SSG — 60 kg, 8.4 V, 180°, full metal brackets (AliExpress)
- XL4005 / XL4015 / XL6009 DC-DC step-up/down converter module
- 3D-printed rollers: https://www.thingiverse.com/thing:5490048
- 3D-printed PSU + Arduino enclosure: https://www.thingiverse.com/thing:5490068

### Optional (recommended)

- 6× 16 V / 16.6 F supercapacitors (3 in series = 8.1 V bank) for current smoothing
- XT60 connectors
- 0.28" 2.5–40 V mini digital voltmeter
- Automotive blade fuse + socket, 10 A

### Power

Servos are driven at 8.2 V — just under the advertised 8.4 V maximum. This gives
fast, quiet response. Supercapacitors smooth current spikes on the DC-DC
converter; charge time is under a minute (initial draw ~4 A for ~5 s, then
rapid decay). Input is 12 V from a shared accessory PSU.

### Servo notes

60 kg servos are recommended. 35 kg servos burn out quickly under sustained full
load. The 180° servos are used over only ~50° of their range; beyond ~60° they
hit full load (~4 A each) and become uncomfortable. They are mounted directly to
3030 aluminium profile under the seat using the supplied metal brackets.

### Mechanical setup

Power the servos **without** USB connection to the PC and mechanically adjust
them so that 0° corresponds to the most relaxed belt position you want.

### Current draw

- Full lock: ~4 A (measured 3.8–4.2 A) per servo
- Normal driving tension: ~2–2.2 A per servo

## Software

### Repository layout

| File | Purpose |
|------|---------|
| `arduino/servo_controller.ino` | Arduino firmware — serial protocol + servo driver |
| `simhub/message.js` | SimHub telemetry expression (the "message" that drives the servos) |
| `scripts/generate_shsds.py` | Generate a `.shsds` profile from `message.js` |
| `scripts/serial_proxy.py` | Serial proxy — sniffs & logs SimHub↔Arduino traffic for analysis |
| `simhub/generated_profile.shsds` | Example generated profile |

### Protocol

Serial link at 9600 baud. Each byte is one of:

| Byte | Meaning |
|------|---------|
| `0` | Next byte = left servo calibration offset |
| `1` | Next byte = right servo calibration offset |
| `≥ 2` | Position command — LSB selects channel (0 = left, 1 = right), bits 1–6 = angle |

The Arduino clamps the final servo angle to 0–180° to prevent PWM-mode overflow
when `position + offset` exceeds 180.

### SimHub setup

1. Load the Arduino sketch onto a Nano (servos on pins 6 and 9).
2. In SimHub, add a **Custom Serial Device**.
3. Generate a profile from the message file:

   ```bash
   python3 scripts/generate_shsds.py simhub/message.js --output simhub/generated_profile.shsds
   ```

4. Import `simhub/generated_profile.shsds` into SimHub.
5. Select the correct COM port for your Arduino in the SimHub device settings.

### Serial proxy (traffic logger)

To log real servo positions during a drive session and analyze them afterwards:

1. **Disable** the Custom Serial Device in SimHub (uncheck "Enabled").
2. Run the proxy — it creates a PTY and connects to the Arduino:

   ```bash
   python3.12 scripts/serial_proxy.py --arduino /dev/ttyUSB1
   ```

3. Repoint Wine COM3 to the PTY slave path printed by the proxy:

   ```bash
   ln -sf /dev/pts/3 ~/.wine/dosdevices/com3
   ```

4. **Re-enable** the SimHub Custom Serial Device.
5. Drive! The proxy logs every byte with timestamp + protocol decode to
   `logs/belt_log_<timestamp>.csv`.
6. Press Ctrl-C to stop. Then analyze:

   ```bash
   python3.12 scripts/serial_proxy.py --analyze logs/belt_log_*.csv
   ```

The analysis prints per-channel min/max/mean angles, a distribution histogram,
offset calibration events, and transient detection (rapid angle jumps that
indicate kick events).

### SimHub settings

All settings appear as sliders and checkboxes in the SimHub Custom Serial Device settings panel.

#### Calibration & core gains

| Setting | Default | Range | Effect |
|---------|---------|-------|--------|
| Left untensioned | 0 | 0–70 | Calibration offset for left servo rest position |
| Right untensioned | 0 | 0–70 | Calibration offset for right servo rest position |
| decel gain | 50 | 0–100 | Scales braking-induced tension (from GlobalAccelerationG) |
| delta yaw gain | 8 | 0–80 | Scales lateral-G-induced tension (from AccelerationSway) |
| smoothing | 2 | 0–4 | IIR low-pass time constant for sustained forces |
| max tension | 60 | 20–127 | Hard cap on servo angle sent over serial |

#### Setup toggles

| Setting | Default | Effect |
|---------|---------|--------|
| Test untensioned positions | off | Hold servos at calibration offsets for setup |
| test max tension | off | Hold servos at max tension for setup |

#### Feature toggles

| Setting | Default | Effect |
|---------|---------|--------|
| Handbrake slackens belts | ON | Slackens both belts when handbrake is pulled |
| Gear-shift kick | ON | Sharp tug on both belts when gear changes |
| Brake-pedal decelerator | off | Uses raw brake pedal (0–1) as deceleration source instead of gLong only |
| Wheel-slip feedback | off | Adds tension when wheels lock up or spin (max slip across all 4 wheels) |
| Suspension bump kick | ON | Adds tug on suspension landing impact (bumps, jumps, kerbs) |
| Pit-limiter slackens belts | ON | Slackens both belts when pit-limiter / speed-limiter is active |
| Pitch/Roll weight transfer | off | Adds body-orientation-based tension (pitch = braking, roll = cornering) |

#### Feature gains

| Setting | Default | Range | Effect |
|---------|---------|-------|--------|
| gear-shift kick gain | 30 | 0–100 | Scales the gear-change kick relative to max tension |
| brake-pedal gain | 40 | 0–100 | Scales brake-pedal decelerator output |
| wheel-slip gain | 20 | 0–100 | Scales wheel-slip feedback |
| bump kick gain | 25 | 0–100 | Scales suspension bump kick |
| pitch weight transfer gain | 10 | 0–50 | Scales pitch-based weight transfer |
| roll weight transfer gain | 10 | 0–50 | Scales roll-based weight transfer |

### Supported SimHub properties

The telemetry script uses these normalized SimHub properties (available across all
supported games, including Gran Turismo 7 via UDP 33739/33740):

- `DataCorePlugin.GameRunning`, `SpeedMph` / `SpeedKmh` — noise gate
- `GlobalAccelerationG`, `AccelerationSway` — sustained G-forces
- `Gear` — gear-shift kick detection
- `Brake` — brake-pedal decelerator
- `Handbrake` — handbrake belt slack
- `SpeedLimiterActive` — pit-limiter belt slack
- `Pitch`, `Roll` — body-orientation weight transfer
- `SuspensionLandingImpactVelocityMs` — bump detection
- `FrontLeftWheelSlip`, `FrontRightWheelSlip`, `RearLeftWheelSlip`, `RearRightWheelSlip` — wheel lockup/spin

## Changes from the original blekenbleu project

- Uses general `AccelerationSway` / `GlobalAccelerationG` properties instead of
  game-specific `GameRawData.Physics.AccG01` / `AccG03` — wider game support.
- **Reset function**: belts stay slack when no game is running (checked via
  `DataCorePlugin.GameRunning`). The original Dirt Rally 2.0 profile left
  residual tension in the belts between sessions.
- Gear-shift kick detected via `Gear` property (direct) instead of gLong derivative.
- Suspension bump kick via `SuspensionLandingImpactVelocityMs`.
- Wheel-slip feedback via per-wheel `WheelSlip` properties.
- Handbrake and pit-limiter automatically slacken belts.
- Optional brake-pedal decelerator and pitch/roll weight transfer.
- All 7 extra features are toggleable via SimHub checkboxes with adjustable gains.
- Delta-guard: no serial output when values are unchanged, eliminating spam.
- Servo angle clamped to 0–180° in firmware (prevents PWM-mode overflow).
- `tmax` has a safe fallback so the protocol can never emit opcode bytes.

## License

See [LICENSE](LICENSE).