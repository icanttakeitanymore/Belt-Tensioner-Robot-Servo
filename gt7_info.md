# Gran Turismo 7 — Telemetry Reference for Belt Tensioner

## Protocol Overview

- **Transport**: UDP, encrypted (Salsa20)
- **Ports**: 33739 (PS5→PC send), 33740 (PC receive/broadcast)
- **Packet size**: 296 bytes encrypted → 252 bytes decrypted
- **Encryption key**: `Simulator Interface Packet GT7 ver 0.0`
- **Magic**: `0x47375330` ("G7S0")
- **Update rate**: ~60 Hz (16.668ms tick interval)
- **Firewall**: Open UDP 33739 and 33740 in/out

## SimHub Integration

- SimHub receives GT7 UDP packets, decrypts, and normalizes into standard properties
- Config: SimHub → Settings → Games → Gran Turismo 7
- Set PS5 IP (Settings → Network → View Connection Status on console)
- SimHub wiki: "GT7: UDP ports 33739 and 33740"

## Packet Structure (252 bytes decrypted)

Source: Nenkai/PDTools (SimulatorPacket.cs), snipem/gt7dashboard (gt7communication.py)

| Offset | Size | Type   | Field                        | Notes                                   |
|--------|------|--------|------------------------------|-----------------------------------------|
| 0x00   | 4    | int32  | magic                        | 0x47375330                              |
| 0x04   | 4    | float  | position_x                   | track position (meters)                 |
| 0x08   | 4    | float  | position_y                   |                                         |
| 0x0C   | 4    | float  | position_z                   |                                         |
| 0x10   | 4    | float  | velocity_x                   | m/s                                     |
| 0x14   | 4    | float  | velocity_y                   | m/s                                     |
| 0x18   | 4    | float  | velocity_z                   | m/s                                     |
| 0x1C   | 4    | float  | rotation_pitch               | radians (-1..1)                          |
| 0x20   | 4    | float  | rotation_yaw                 | radians (-1..1)                          |
| 0x24   | 4    | float  | rotation_roll                | radians (-1..1)                          |
| 0x28   | 4    | float  | rel_orientation_north        |                                         |
| 0x2C   | 4    | float  | angular_velocity_x           | rad/s                                   |
| 0x30   | 4    | float  | angular_velocity_y           | rad/s                                   |
| 0x34   | 4    | float  | angular_velocity_z           | rad/s                                   |
| 0x38   | 4    | float  | body_height                  | meters                                  |
| 0x3C   | 4    | float  | rpm                          | engine RPM                              |
| 0x40   | 8    | bytes  | IV (Salsa20)                 | initialization vector                   |
| 0x48   | 4    | float  | unknown                      |                                         |
| 0x4C   | 4    | float  | speed                        | m/s (×3.6 = km/h)                       |
| 0x50   | 4    | float  | turbo_boost                  | <1.0 = boost, 2.0 = 1 bar               |
| 0x54   | 4    | float  | oil_pressure                 | bars                                    |
| 0x58   | 4    | float  | water_temp                   | always ~85                              |
| 0x5C   | 4    | float  | oil_temp                     | always ~110                             |
| 0x60   | 4    | float  | tire_temp_FL                 | °C                                      |
| 0x64   | 4    | float  | tire_temp_FR                 | °C                                      |
| 0x68   | 4    | float  | tire_temp_RL                 | °C                                      |
| 0x6C   | 4    | float  | tire_temp_RR                 | °C                                      |
| 0x70   | 4    | int32  | packet_id                    | for ordering                            |
| 0x74   | 2    | int16  | current_lap                  |                                         |
| 0x76   | 2    | int16  | laps_in_race                 |                                         |
| 0x78   | 4    | int32  | best_lap_time                | ms (-1 if not set)                      |
| 0x7C   | 4    | int32  | last_lap_time                | ms (-1 if not set)                      |
| 0x80   | 4    | int32  | time_of_day                  | ms                                      |
| 0x84   | 2    | int16  | pre_race_start_position       | -1 after race start                      |
| 0x86   | 2    | int16  | num_cars_pre_race            | -1 after race start                      |
| 0x88   | 2    | int16  | min_alert_rpm                | rev warning min                          |
| 0x8A   | 2    | int16  | max_alert_rpm                | rev limiter max                           |
| 0x8C   | 2    | int16  | calculated_max_speed         | depends on transmission                  |
| 0x8E   | 2    | int16  | flags                        | bitfield (see below)                     |
| 0x90   | 1    | byte   | gear_bits                    | low 4 bits = gear, high 4 = suggested    |
| 0x91   | 1    | byte   | throttle                     | 0-255                                   |
| 0x92   | 1    | byte   | brake                        | 0-255                                   |
| 0x93   | 1    | byte   | unknown                      |                                         |
| 0x94   | 4    | float  | tire_unknown_FL              |                                         |
| 0x98   | 4    | float  | tire_unknown_FR              |                                         |
| 0x9C   | 4    | float  | tire_unknown_RL              |                                         |
| 0xA0   | 4    | float  | tire_unknown_RR              |                                         |
| 0xA4   | 4    | float  | wheel_rps_FL                 | wheel rev/s (radians)                    |
| 0xA8   | 4    | float  | wheel_rps_FR                 |                                         |
| 0xAC   | 4    | float  | wheel_rps_RL                 |                                         |
| 0xB0   | 4    | float  | wheel_rps_RR                 |                                         |
| 0xB4   | 4    | float  | tire_radius_FL               | meters                                  |
| 0xB8   | 4    | float  | tire_radius_FR               | meters                                  |
| 0xBC   | 4    | float  | tire_radius_RL               | meters                                  |
| 0xC0   | 4    | float  | tire_radius_RR               | meters                                  |
| 0xC4   | 4    | float  | suspension_height_FL         |                                         |
| 0xC8   | 4    | float  | suspension_height_FR         |                                         |
| 0xCC   | 4    | float  | suspension_height_RL         |                                         |
| 0xD0   | 4    | float  | suspension_height_RR         |                                         |
| 0xF4   | 4    | float  | clutch_pedal                 | 0.0-1.0                                 |
| 0xF8   | 4    | float  | clutch_engaged               | 0.0-1.0                                 |
| 0xFC   | 4    | float  | rpm_clutch_gearbox          | RPM after clutch                         |
| 0x104  | 32   | float  | gear_ratios[8]               | up to 8 gears                           |
| 0x124  | 4    | int32  | car_code                     | car ID                                  |

## Flags (0x8E, int16)

| Bit | Flag                          | Description                              |
|-----|-------------------------------|------------------------------------------|
| 0   | CarOnTrack                    | Car on track or paddock                  |
| 1   | Paused                        | Simulation paused (not in online modes)  |
| 2   | LoadingOrProcessing           | Track/car loading                        |
| 3   | InGear                        | Gear engaged                             |
| 4   | HasTurbo                      | Car has turbo                            |
| 5   | RevLimiterBlinkAlertActive    | Rev limiter active                       |
| 6   | HandBrakeActive               | Handbrake pulled                         |
| 7   | LightsActive                  | Lights on                                |
| 8   | HighBeamActive                | High beams on                            |
| 9   | LowBeamActive                 | Low beams on                              |
| 10  | ASMActive                     | Active Stability Management              |
| 11  | TCSActive                    | Traction Control System                  |

## Derived Values

- **Car speed (km/h)**: speed × 3.6
- **Wheel speed (km/h)**: |3.6 × tire_radius × wheel_rps|
- **Tire slip ratio**: wheel_speed / car_speed (1.0 = no slip, >1.0 = lock, <1.0 = spin)
- **Throttle %**: throttle / 2.55
- **Brake %**: brake / 2.55
- **Gear**: gear_bits & 0x0F (low nibble)
- **Suggested gear**: gear_bits >> 4 (high nibble, 15 = no suggestion)

## Sources

- Nenkai/PDTools — definitive C# spec: https://github.com/Nenkai/PDTools
- snipem/gt7dashboard — Python parser: https://github.com/snipem/gt7dashboard
- gt7coder/grandturismo-srs-proxy — GT7→SRS proxy: https://github.com/gt7coder/grandturismo-srs-proxy
- GTPlanet discovery thread: https://www.gtplanet.net/forum/threads/gt7-is-compatible-with-motion-rig.410728
- SimHub wiki (GT7 config): https://github.com/SHWotever/SimHub/wiki/SimHub-Basics----Games-config-and-troubleshooting