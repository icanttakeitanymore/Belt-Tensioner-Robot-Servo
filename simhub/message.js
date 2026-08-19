var run = $prop('DataCorePlugin.GameRunning'), speed = $prop('SpeedMph') || $prop('SpeedKmh') || 0;
var gLong = $prop('GlobalAccelerationG') || 0;
var active = (run && speed > 1);

// --- Gate helpers ---
var hb = $prop('Handbrake');
var gear = $prop('Gear') || 0;
var brake = $prop('Brake') || 0;
var pitch = $prop('Pitch') || 0;
var roll = $prop('Roll') || 0;
var pitLim = $prop('SpeedLimiterActive');

// 1. Extract raw sustained forces (Noise Gated)
var lat = active ? $prop('AccelerationSway') * $prop('Settings.yaw_gain') : 0;
var dec = active ? Math.max(0, -gLong * $prop('Settings.decel_gain')) : 0;

// 1b. Optional: brake-pedal decelerator (uses raw brake pedal 0-1 instead of gLong)
if ($prop('Settings.enable_brake_pedal')) {
    var bp = active ? brake * $prop('Settings.brake_pedal_gain') : 0;
    dec = Math.max(dec, bp);
}

// 1c. Optional: pitch/roll weight transfer (adds body-orientation-based tension)
if ($prop('Settings.enable_pitch_roll')) {
    var pAdd = active ? Math.abs(pitch) * $prop('Settings.pitch_gain') : 0;
    var rAdd = active ? roll * $prop('Settings.roll_gain') : 0;
    dec += pAdd;
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

// 4. High-pass transient: gear-shift kick (replaces gLong-derivative kick)
var kick = 0;
if ($prop('Settings.enable_gear_kick') && active) {
    var lastGear = root["lastGear"] || gear;
    if (gear !== lastGear && gear > 0) {
        kick = $prop('Settings.gear_kick_gain') / 100 * ($prop('Settings.tmax') || 60);
    }
    root["lastGear"] = gear;
}
// Keep wasActive guard for gLong-based kick fallback
var acc = active ? Math.max(0, gLong) : 0;
var lastAcc = root["lastAcc"] || 0;
var wasActive = root["wasActive"] || false;
if (active && wasActive && acc > lastAcc && kick === 0) {
    kick = (acc - lastAcc) * 30;
}
root["lastAcc"] = acc;
root["wasActive"] = active;

// 4b. Optional: suspension bump kick (landing impact)
if ($prop('Settings.enable_bump') && active) {
    var bump = $prop('SuspensionLandingImpactVelocityMs') || 0;
    var lastBump = root["lastBump"] || 0;
    if (bump > lastBump && bump > 0.5) {
        kick += bump * $prop('Settings.bump_gain') / 100 * ($prop('Settings.tmax') || 60);
    }
    root["lastBump"] = bump;
}

// 4c. Optional: wheel-slip feedback (brake lockup or wheelspin)
if ($prop('Settings.enable_wheelslip') && active) {
    var slipFL = $prop('FrontLeftWheelSlip') || 0;
    var slipFR = $prop('FrontRightWheelSlip') || 0;
    var slipRL = $prop('RearLeftWheelSlip') || 0;
    var slipRR = $prop('RearRightWheelSlip') || 0;
    var maxSlip = Math.max(Math.abs(slipFL), Math.abs(slipFR), Math.abs(slipRL), Math.abs(slipRR));
    if (maxSlip > 0.1) {
        kick += maxSlip * $prop('Settings.wheelslip_gain') / 100 * ($prop('Settings.tmax') || 60);
    }
}

// Reset persistent cache in UI calibration test modes
if ($prop('Settings.max_test') || $prop('Settings.TestOffsets')) {
    root["sl"] = root["sr"] = root["lastL"] = root["lastR"] = root["lastAcc"] = root["wasActive"] = null;
    root["lastGear"] = root["lastBump"] = null;
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
var tmax = ($prop('Settings.tmax') || 60) & 126;
l = Math.min(tmax, Math.max(2, finalL)) & 126;
r = Math.min(tmax, Math.max(3, finalR)) | 1;

// 7. Delta transmission guard to eliminate silent serial spam
if (l === root["lastL"] && r === root["lastR"]) return "";
root["lastL"] = l; root["lastR"] = r;

return String.fromCharCode(l, r);