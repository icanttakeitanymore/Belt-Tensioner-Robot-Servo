# SimHub — Reference for Belt Tensioner Project

## Overview

SimHub is a sim racing telemetry application that normalizes game data across
all supported titles. For our project, it receives GT7 UDP telemetry and drives
a Custom Serial Device (Arduino Nano with belt tensioner servos).

- Downloads: http://www.simhubdash.com/
- Manual: https://manual.simhubdash.com/
- Wiki: https://github.com/SHWotever/SimHub/wiki
- Forum: https://www.simhubdash.com/community-2/
- Issues: https://github.com/zegreatclan/SimHub/issues

## Custom Serial Device

Our project uses the **Custom Serial Device** plugin (not the Motion addon's
Generic Serial Controller). The Custom Serial Device sends user-defined JS/NCalc
expressions over a COM port.

### Enabling

SimHub → Settings → Plugins → enable "Custom Serial Devices"

### Key Documentation

- Generic Serial Controller (Motion addon):
  https://manual.simhubdash.com/motion-addon/supported-controllers/generic-serial-controller.md
- Device communication protocols:
  https://manual.simhubdash.com/device-definition-authoring/device-communication-protocols.md
- Custom serial devices wiki:
  https://github.com/SHWotever/SimHub/wiki/Custom-serial-devices

### Serial Settings

| Setting      | Our value | Notes                                              |
|--------------|-----------|----------------------------------------------------|
| Baudrate     | 9600      | Matches Arduino sketch                             |
| DTR          | OFF       | Arduino Nano resets on DTR assert; disabling prevents connection-time reboot |
| RTS          | ON        | Required by many USB-to-serial chips (CH340)       |
| Startup delay| 2000 ms   | Safety margin for USB-serial initialization        |

### Command Phases

| Phase           | Our usage                              |
|-----------------|----------------------------------------|
| OnConnect       | `' !'` — handshake marker              |
| UpdateMessages  | 2 messages: offset calibration + telemetry |
| OnDisconnect    | `' !'` — handshake marker              |

### Expression Engine

Custom Serial Device supports two interpreters:
- **Interpreter 1** (JavaScript) — used in our project. Supports `$prop()`,
  `root[]` persistent state, `String.fromCharCode()` for byte-packing.
- NCalc — limited: no string operators, no byte values, integers sent as decimal
  strings. blekenbleu documented why JS is needed for bit-packing.

### Settings Panel

Custom Serial Device supports user-defined settings (sliders + checkboxes)
via SettingsBuilder. These appear in the SimHub UI and are accessible in
expressions via `$prop('Settings.<PropertyName>')`.

Our profile has 21 settings: 6 core gains, 2 setup toggles, 7 feature toggles,
6 feature gains.

## SimHub Normalized Properties

Source: GameReaderCommon.dll decompiled from SimHub SDK
(https://github.com/jtexp/simhub-sdk). These properties are available across
ALL supported games (including GT7) with prefix `DataCorePlugin.GameData.*`
or directly by name in `$prop()`.

### Properties Used by Belt Tensioner

| Property                          | Type   | Description                                  |
|-----------------------------------|--------|----------------------------------------------|
| DataCorePlugin.GameRunning        | bool   | Game running flag (noise gate)               |
| SpeedMph / SpeedKmh               | float  | Vehicle speed (noise gate)                   |
| GlobalAccelerationG              | float  | Longitudinal acceleration in G (decel = negative) |
| AccelerationSway                   | float  | Lateral acceleration (cornering)             |
| Gear                              | int    | Current gear (gear-shift kick detection)      |
| Brake                             | float  | Brake pedal 0-1 (brake-pedal decelerator)     |
| Handbrake                         | bool   | Handbrake active (slacken belts)              |
| SpeedLimiterActive                | bool   | Pit-limiter / speed limiter (slacken belts)   |
| Pitch                             | float  | Body pitch orientation (weight transfer)     |
| Roll                              | float  | Body roll orientation (weight transfer)       |
| SuspensionLandingImpactVelocityMs | float  | Suspension bump/landing impact (bump kick)    |
| FrontLeftWheelSlip                | float  | Wheel slip FL (lockup/spin feedback)          |
| FrontRightWheelSlip               | float  | Wheel slip FR                                 |
| RearLeftWheelSlip                 | float  | Wheel slip RL                                 |
| RearRightWheelSlip                | float  | Wheel slip RR                                 |

### Other Available Properties (not used)

**Pedals/Controls**: Throttle, Clutch, Handbrake, GearGrinding, GearNumber

**Motion/Acceleration**: AccelerationSurge, AccelerationHeave, LateralAcceleration,
LongitudinalAcceleration, VerticalAcceleration, WorldAccelerationZ,
WorldAccelerationZSmoothed

**Orientation**: OrientationPitch, OrientationRoll, OrientationYaw,
OrientationYawChangePerSecond, OrientationYawVelocity, PitchRate, RollRate,
YawRate, PitchChangeVelocity, RollChangeVelocity, YawChangeVelocity

**Wheels**: WheelSlip, WheelsSlip, WheelRPS, WheelsRPS, WheelSpeed, WheelsSpeed,
WheelRumble, WheelsRumble, WheelInGrassOrGravel, WheelsOnKerbs
(per-wheel: FrontLeft/Right, RearLeft/Right variants for all)

**Suspension**: SuspensionPosition, SuspensionVelocity, SuspensionVelocityMs,
SuspensionLandingImpactVelocityMs, SuspensionPositionMax/Min
(per-wheel: FrontLeft/Right, RearLeft/Right variants)

**Engine**: Rpms, MaxRpm, UpshiftRpm, ShiftLight1, ShiftLight2, Turbo,
TurboBar, TurboPercent, MaxTurbo, MaxTurboBar

**Temperatures**: WaterTemperature, OilTemperature, OilPressure,
RoadTemperature, AirTemperature, TireTemperatureFL/FR/RL/RR
(inner/middle/outer per wheel), BrakeTemperatureFL/FR/RL/RR

**Tires**: TyrePressureFL/FR/RL/RR, TyresTemperatureAvg/Max/Min

**Fuel**: Fuel, FuelPercent, MaxFuel, EstimatedFuelRemaingLaps,
FuelConsumption, FuelRaw

**Laps/Position**: Position, LapNumber, CurrentLapTime, BestLapTime,
LastLapTime, CompletedLaps, TotalLaps, TrackPositionPercent,
PlayerLeaderboardPosition, RacePositionGain

**Flags**: GamePaused, IsPaused, RunningGameProcessDetected,
SpeedLimiterActive, GearGrinding

## .shsds Profile Format

SimHub Custom Serial Device profiles are JSON files (`.shsds`).
Stored in `Documents/SimHub/` folder.

Key fields:
- `SerialPortName`: COM port (e.g. "COM3")
- `BaudRate`: 9600
- `DtrEnable` / `RtsEnable`: serial line control
- `StartupDelayMs`: delay after port open before sending
- `UpdateMessages[]`: array of message definitions
  - `Message.Expression`: JS/NCalc expression
  - `Message.Interpreter`: 1 = JavaScript
  - `MaximumFrequency`: 0 = unlimited
- `OnConnectMessage` / `OnDisconnectMessage`: one-time messages
- `SettingsBuilder.Settings[]`: user-facing settings array
  - `TypeName`: "SliderEntry" or "BoolEntry"
  - `PropertyName`: name for `$prop('Settings.<name>')`
  - `CurrentValue`: default value
  - `Maximum` / `Minimum`: slider range

## Wine Setup

SimHub runs under Wine on Linux. Serial ports are mapped via symlinks:

```
~/.wine/dosdevices/com3 → /dev/ttyUSB1   (belt tensioner Arduino)
~/.wine/dosdevices/com33 → /dev/ttyUSB0  (other device)
```

Check Arduino connectivity:
```bash
# Find CH340 devices
lsusb | grep 1a86
# Map to COM ports
ls -la ~/.wine/dosdevices/com*
# Verify Arduino responds (should print "belt servos: connected")
stty -F /dev/ttyUSB1 9600 raw -echo && cat /dev/ttyUSB1
```

## References

- blekenbleu original project: https://blekenbleu.github.io/Arduino/SimHubCustomSerial
- blekenbleu SimHub profiles: https://github.com/blekenbleu/SimHub-Profiles
- blekenbleu SimHubG.js: https://github.com/blekenbleu/blekenbleu.github.io/blob/master/Arduino/SimHubG.js.txt
- SimHub SDK DLLs: https://github.com/jtexp/simhub-sdk
- blekenbleu SimHubPluginSdk: https://github.com/blekenbleu/SimHubPluginSdk
- SimHub property server plugin: https://github.com/pre-martin/SimHubPropertyServer
- CalcLngWheelSlip plugin: https://github.com/blekenbleu/CalcLngWheelSlip
- NCalc reference: http://www.codeproject.com/KB/recipes/sota_expression_evaluator.aspx