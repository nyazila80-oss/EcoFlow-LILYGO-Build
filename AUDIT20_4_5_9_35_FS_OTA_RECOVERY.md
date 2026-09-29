# AUDIT 20.4.5.9.35 — FS OTA RECOVERY

Hardware finding from real PlatformIO uploadfsota:
- firmware OTA succeeded
- filesystem OTA connected then failed at 0% / WinError 10054
- firmware remained reachable and reported FS_VERSION_MISMATCH

Root cause found in source:
- PlatformIO uploadfsota uses ArduinoOTA with U_SPIFFS.
- SPIFFS remained mounted in the ArduinoOTA path.
- The separate HTTP /ota_fs path already called SPIFFS.end(), but uploadfsota does not use that path.

Fix:
- ArduinoOTA.onStart checks ArduinoOTA.getCommand().
- U_SPIFFS explicitly calls SPIFFS.end() before filesystem update.
- ArduinoOTA.onError attempts SPIFFS.begin(false) so a failed FS OTA can recover the old filesystem without a mandatory reboot.
- Firmware OTA behavior remains unchanged.

Safety:
- no CAN/BMS/BLE/resource-gate behavior changed.
- no partition-table change.
- OTA remains authenticated.
