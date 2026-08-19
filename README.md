# Belt-Tensioner-Robot-Servo

Sim Racing Belt Tensioner using robot hobby servos and SimHub.

Based on the original project by [blekenbleu](https://github.com/blekenbleu) —
[SimHub Custom serial device for Blue Pill](https://blekenbleu.github.io/Arduino/SimHubCustomSerial).

## What it does

Two high-torque hobby servos pull your shoulder harnesses based on live telemetry
from SimHub. Braking tightens both belts; cornering tightens the outside belt.
A high-pass transient channel adds a sharp tug on gear shifts and clutch bites.

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

### SimHub settings (sliders)

| Setting | Default | Range | Effect |
|---------|---------|-------|--------|
| Left untensioned | 0 | 0–70 | Calibration offset for left servo rest position |
| Right untensioned | 0 | 0–70 | Calibration offset for right servo rest position |
| decel gain | 50 | 0–100 | Scales braking-induced tension |
| delta yaw gain | 8 | 0–80 | Scales lateral-G-induced tension |
| smoothing | 2 | 0–4 | IIR low-pass time constant for sustained forces |
| max tension | 60 | 20–127 | Hard cap on servo angle sent over serial |
| Test untensioned positions | off | — | Hold servos at calibration offsets for setup |
| test max tension | off | — | Hold servos at max tension for setup |

## Changes from the original blekenbleu project

- Uses general `AccelerationSway` / `GlobalAccelerationG` properties instead of
  game-specific `GameRawData.Physics.AccG01` / `AccG03` — wider game support.
- **Reset function**: belts stay slack when no game is running (checked via
  `DataCorePlugin.GameRunning`). The original Dirt Rally 2.0 profile left
  residual tension in the belts between sessions.
- High-pass transient channel for gear shifts / clutch bite ("kick").
- Delta-guard: no serial output when values are unchanged, eliminating spam.
- Servo angle clamped to 0–180° in firmware (prevents PWM-mode overflow).
- `tmax` has a safe fallback so the protocol can never emit opcode bytes.

## License

See [LICENSE](LICENSE).