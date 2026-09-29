# 9.36.4 NO-WEB-AUTH A/B — focused FMEA

| Failure mode | Effect | Containment in 9.36.4 | Residual risk |
|---|---|---|---|
| Browser Basic-Auth challenge/retry storm | UI stalls/extra HTTP load | Web/API Basic Auth removed, so no 401 challenge path | Other TCP/Web causes remain possible |
| WebSocket Basic-Auth handshake/retry | WS reconnect churn | WS setAuthentication removed | Generic WS reconnect churn remains possible |
| Unauthenticated LAN client accesses UI/API | Read/control access from reachable LAN | Diagnostic release only; same-origin retained for mutations | Any LAN client can intentionally operate UI/API |
| Cross-site browser mutation | Unwanted POST from unrelated origin | remoteMutationAllowed same-origin guard retained | Not an authentication boundary |
| Browser firmware OTA becomes open | Unauthorized firmware write | Dedicated remoteOtaAuthRequest retained; upload callback also authenticates | Password secrecy still required |
| Browser filesystem OTA becomes open | Unauthorized SPIFFS write | Dedicated remoteOtaAuthRequest retained; upload callback also authenticates | Password secrecy still required |
| ArduinoOTA becomes open | Unauthorized network OTA | ArduinoOTA.setPassword retained | Password secrecy still required |
| Recovery AP becomes open | Nearby access to AP | WPA password still derived from remoteAuthPassword | Existing password handling unchanged |
| Auth change affects CAN/BMS/SOC/BLE safety | Battery-control regression | No changes in those modules; regression sims rerun | Hardware validation still required |
| FS/FW version skew | UI/backend mismatch | fs_version updated to exact FW_VERSION | Requires flashing matching FS |
