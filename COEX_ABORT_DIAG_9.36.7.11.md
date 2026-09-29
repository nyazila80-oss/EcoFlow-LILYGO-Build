# Hardware finding and coex diagnostic candidate — 2026-09-25

Uploaded monitor: JK 308-byte status frames repeatedly validate; CAN drops 0; Wi-Fi connects; immediately after `[JK-BLE] AUDIT19.15.29... init` around 20.9 s, ESP32 aborts in `coex_core_enable -> coex_enable -> esp_bt_controller_enable -> NimBLEDevice::init`. Boot repeats. The compiled NimBLE config log is not reached because `init` does not return.

Source finding: `src/wi-fi.cpp` called `WiFi.setSleep(false)` at initial STA, recovery AP+STA and both return-to-STA paths. The pinned Arduino-ESP32 WiFiGeneric implementation maps false to `WIFI_PS_NONE`, true to `WIFI_PS_MIN_MODEM`. An Espressif IDF issue documents this exact abort stack after Wi-Fi is connected, `WIFI_PS_NONE` is selected and NimBLE initializes: https://github.com/espressif/esp-idf/issues/9595 . This is a strong root-cause hypothesis, not yet confirmed on the user's LILYGO.

Change in this candidate: all four paths use `WiFi.setSleep(true)`; no JK parser, CAN, BMS limits, BLE roles, worker scheduling or credentials changed. No NVS erase. The change can affect Wi-Fi latency and needs hardware observation.

PlatformIO 6.2.0: Full Clean + serial (`-j 1`) compile/link PASS for `lilygo_tcan485`; RAM 89,116/327,680 B; program 1,538,909/1,835,008 B. An earlier parallel clean build produced an empty powerstream_ble_lab object and link failure; explicit recompilation passed, then the full serial clean build passed. This candidate is unflashed and untested on the device.

Next controlled gate: upload only firmware to the already compatible partition layout, retain existing SPIFFS/NVS, capture boot through at least the 20-second JK-BLE init and 60 seconds of heartbeat. Confirm `[JK-BLE] compiled config maxConn=2 observer=0 mtu=247`, no abort/reboot, Wi-Fi/WebUI heartbeat, heap/largest8/min and JK/CAN counters. Stop before cloud/PS-BLE commands. If abort remains, retain entire serial monitor and exact built ELF for decoding; do not advance to C1/C2/D.
