# 9.36.4 NO-WEB-AUTH-AB

Controlled A/B diagnostic against 9.36.3.

- Local HTTP WebUI/API: Basic Auth disabled.
- WebSockets /log, /bms, /debug: Basic Auth disabled.
- Same-origin guard for mutating HTTP endpoints remains enabled.
- ArduinoOTA: password remains enabled.
- Browser firmware OTA /ota_update and filesystem OTA /ota_fs: password remains enabled, including upload callbacks.
- Recovery/setup AP WPA password remains unchanged.
- PowerStream BLE UI and backend remain present.
- CAN/BMS/SOC/BLE protocol/recovery logic unchanged.

Security note: any device with network access to the bridge can read/control non-OTA WebUI/API during this diagnostic release. Do not expose HTTP port 80 to the Internet.
