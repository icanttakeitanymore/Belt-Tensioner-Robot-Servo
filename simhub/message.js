var run = $prop('DataCorePlugin.GameRunning'), speed = $prop('SpeedMph') || $prop('SpeedKmh') || 0;
var gLong = $prop('GlobalAccelerationG') || 0;
var active = (run && speed > 1);

// --- Gate helpers (with fallbacks) ---
var hb = $prop('Handbrake') || false;
var gear = $prop('Gear') || 0;
var brake = $prop('Brake') || 0;
var pitch = $prop('Pitch') || 0;
var roll = $prop('Roll') || 0;
var pitLim = $prop('SpeedLimiterActive') || false;

// 1. Extract raw sustained forces (Noise Gated)
var lat = active ? $prop('AccelerationSway') * $prop('Settings.yaw_gain') : 0;
var dec = active ? Math.max(0, -gLong * $prop('Settings.decel_gain')) : 0;

// 1b. Optional: brake-pedal decelerator (uses raw brake pedal 0-1 instead of gLong)
if ($prop('Settings.enable_brake_pedal')) {
    var bp = active ? brake * $prop('Settings.brake_pedal_gain') : 0;
    dec = Math.max(dec, bp);
}

// 1c. Optional: pitch/roll weight transfer
// Pitch and roll are body orientation, NOT acceleration.
// They add directional tension: pitch (brake dives nose) → both belts,
// roll (cornering leans) → outside belt only.
if ($prop('Settings.enable_pitch_roll')) {
    var pAdd = active ? Math.abs(pitch) * $prop('Settings.pitch_gain') : 0;
    var rAdd = active ? roll * $prop('Settings.roll_gain') : 0;
    // pitch adds to deceleration channel (both belts via weight transfer)
    dec += pAdd;
    // roll adds to lateral channel (directional, sign preserved)
    lat += rAdd;
}

// 2. Vector distribution for weight transfer
var r = Math.sqrt(dec * dec + lat * lat), l = Math.max(0, (dec * 2) - r);
if (lat < 0) { var tmp = r; r = l; l = tmp; }

// 3. Low-pass IIR filter for smooth sustained sensations
if (root["sl"] == null || root["sr"] == null) { root["sr"] = r; root["sl"] = l; }
var tc = Math.max(1.0, 1.0 + ($prop('Settings.smooth') || 0));

var diffR = r - root["sr"]; root["sr"] += Math.abs(diffR) < 0.05 ? diffR : (diffR / tc);
var diffL = l - root["sl"]; root["sl"] += Math.abs(diffL) < 0.05 ? diffL : (diffL / tc);

// 4. Transient kick engine with exponential decay
// Kick persists across frames: each frame new kick is added, then decayed.
// This gives servos time to physically respond (~60-100ms) instead of a 1-frame spike.
var tmaxRaw = $prop('Settings.tmax') || 60;
var kickDecay = 0.6; // 60% remains each frame → ~3 frames at 60Hz = ~50ms tail
var kick = (root["kick"] || 0) * kickDecay;

// 4a. Gear-shift kick (direct gear change detection)
if ($prop('Settings.enable_gear_kick') && active) {
    var lastGear = root["lastGear"] || gear;
    if (gear !== lastGear && gear > 0) {
        kick += $prop('Settings.gear_kick_gain') / 100 * tmaxRaw;
    }
    root["lastGear"] = gear;
}

// 4b. gLong-derivative kick (acceleration surge, e.g. clutch bite)
// Can coexist with gear kick — both are valid transients
var acc = active ? Math.max(0, gLong) : 0;
var lastAcc = root["lastAcc"] || 0;
var wasActive = root["wasActive"] || false;
if (active && wasActive && acc > lastAcc) {
    kick += (acc - lastAcc) * 30;
}
root["lastAcc"] = acc;
root["wasActive"] = active;

// 4c. Optional: suspension bump kick (rising-edge detection)
if ($prop('Settings.enable_bump') && active) {
    var bump = $prop('SuspensionLandingImpactVelocityMs') || 0;
    var lastBump = root["lastBump"] || 0;
    // Only trigger on rising edge: bump must exceed lastBump AND a threshold
    // This prevents re-triggering while bump value oscillates
    if (bump > lastBump * 1.5 && bump > 0.5) {
        kick += (bump - lastBump) * $prop('Settings.bump_gain') / 100 * tmaxRaw;
    }
    root["lastBump"] = bump;
}

// 4d. Optional: wheel-slip feedback (brake lockup or wheelspin)
if ($prop('Settings.enable_wheelslip') && active) {
    var slipFL = $prop('FrontLeftWheelSlip') || 0;
    var slipFR = $prop('FrontRightWheelSlip') || 0;
    var slipRL = $prop('RearLeftWheelSlip') || 0;
    var slipRR = $prop('RearRightWheelSlip') || 0;
    var maxSlip = Math.max(Math.abs(slipFL), Math.abs(slipFR), Math.abs(slipRL), Math.abs(slipRR));
    if (maxSlip > 0.1) {
        kick += maxSlip * $prop('Settings.wheelslip_gain') / 100 * tmaxRaw;
    }
}

// Store decayed kick for next frame
root["kick"] = kick;

// Reset persistent cache in UI calibration test modes
if ($prop('Settings.max_test') || $prop('Settings.TestOffsets')) {
    root["sl"] = root["sr"] = root["lastL"] = root["lastR"] = root["lastAcc"] = root["wasActive"] = null;
    root["lastGear"] = root["lastBump"] = root["kick"] = root["off"] = null;
    return "";
}

// 5. Bypass injection: add transient kick to filtered values
var finalL = root["sl"] + kick;
var finalR = root["sr"] + kick;

// 5b. Handbrake → slacken belts
if ($prop('Settings.enable_handbrake') && hb) {
    finalL = 2; finalR = 3;
}

// 5c. Pit-limiter → slacken belts
if ($prop('Settings.enable_pit_limiter') && pitLim) {
    finalL = 2; finalR = 3;
}

// 6. Boundaries mapping & dynamic bit-packing (Left even, Right odd)
var tmax = tmaxRaw & 126;
l = Math.min(tmax, Math.max(2, finalL)) & 126;
r = Math.min(tmax, Math.max(3, finalR)) | 1;

// 7. Delta transmission guard to eliminate silent serial spam
if (l === root["lastL"] && r === root["lastR"]) return "";
root["lastL"] = l; root["lastR"] = r;

return String.fromCharCode(l, r);