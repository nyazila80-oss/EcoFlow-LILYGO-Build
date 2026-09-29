# AUDIT20.4.5.9.11 — wrap/AP+STA/cross-core sweep

## Findings fixed
1. JK BLE WiFi admission/reconnect checks handled only WIFI_STA, not WIFI_AP_STA. In recovery AP+STA, JK BLE could initialize/reconnect while STA was disconnected. Both checks now treat STA and AP+STA equivalently.
2. NTP monotonic interpolation stored the 32-bit Arduino `micros()` sample in a 64-bit variable and subtracted with 64-bit promotion. At the ~71.6 minute `micros()` wrap, this could underflow to a huge delta. The interpolation now uses ESP-IDF `esp_timer_get_time()` (64-bit monotonic microseconds), removing the ~71.6 minute Arduino `micros()` wrap from this path entirely.

## Cross-core sweep
- EcoFlow dynamic power fields use the existing atomic CAN power snapshot, not the raw `inputWatt/outputWatt` globals.
- BMS safety data used by the PS worker is published through the 9.10 safety snapshot.
- CAN battery snapshot writers remain serialized by the 9.10 writer mux.
- Remaining direct `config` reads in Web/MQTT are presentation/control-plane data and are not used as the new PS physical-enforcement proof. They remain a cleanup candidate rather than a newly identified safety-path defect.

## Limitations
- No PlatformIO compiler is available in this environment; no compile success is claimed.
- No hardware validation is claimed.
- Automatic 20/25 SOC control remains disabled.

3. **AsyncWebServer/main-loop String races (WiFi + MQTT).** Web callbacks previously mutated `net.wifiSsid/net.wifiPass` and called `loadMqttConfig()` while the main loop could concurrently read the same Arduino `String` objects. This is a real allocator/object data race. 9.11 persists NVS from the web task but defers all runtime String mutation/application to the main loop through atomic pending flags.
