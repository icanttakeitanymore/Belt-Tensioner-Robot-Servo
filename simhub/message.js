var run = $prop('DataCorePlugin.GameRunning'), speed = $prop('SpeedMph') || $prop('SpeedKmh') || 0;
var gLong = $prop('GlobalAccelerationG') || 0;

// 1. Extract raw sustained forces (Noise Gated)
var lat = (run && speed > 1) ? $prop('AccelerationSway') * $prop('Settings.yaw_gain') : 0;
var dec = (run && speed > 1) ? Math.max(0, -gLong * $prop('Settings.decel_gain')) : 0;

// 2. Vector distribution for weight transfer
var r = Math.sqrt(dec * dec + lat * lat), l = Math.max(0, (dec * 2) - r);
if (lat < 0) { var tmp = r; r = l; l = tmp; }

// 3. Low-pass IIR filter for smooth sustained sensations
if (root["sl"] == null || root["sr"] == null) { root["sr"] = r; root["sl"] = l; }
var tc = Math.max(1.0, 1.0 + ($prop('Settings.smooth') || 0));

var diffR = r - root["sr"]; root["sr"] += Math.abs(diffR) < 0.05 ? diffR : (diffR / tc);
var diffL = l - root["sl"]; root["sl"] += Math.abs(diffL) < 0.05 ? diffL : (diffL / tc);

// 4. High-pass filter for instant transients (Gear shifts / Clutch bites)
var active = (run && speed > 1);
var acc = active ? Math.max(0, gLong) : 0;
var lastAcc = root["lastAcc"] || 0;
var wasActive = root["wasActive"] || false;
// Suppress kick on first active frame after idle — lastAcc is stale from a previous session
var kick = (active && wasActive && acc > lastAcc) ? (acc - lastAcc) * 30 : 0;
root["lastAcc"] = acc;
root["wasActive"] = active;

// Reset persistent cache environments in UI calibration test modes
if ($prop('Settings.max_test') || $prop('Settings.TestOffsets')) {
    root["sl"] = root["sr"] = root["lastL"] = root["lastR"] = root["lastAcc"] = root["wasActive"] = null; return "";
}

// 5. Bypass injection: Add transient kick directly to filtered values
var finalL = root["sl"] + kick;
var finalR = root["sr"] + kick;

// Boundaries mapping & dynamic bit-packing (Left even, Right odd)
var tmax = ($prop('Settings.tmax') || 60) & 126;
l = Math.min(tmax, Math.max(2, finalL)) & 126;
r = Math.min(tmax, Math.max(3, finalR)) | 1;

// 6. Delta transmission guard to eliminate silent serial spam
if (l === root["lastL"] && r === root["lastR"]) return "";
root["lastL"] = l; root["lastR"] = r;

return String.fromCharCode(l, r);