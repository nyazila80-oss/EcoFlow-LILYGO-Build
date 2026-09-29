# OpenAPI quota/all diagnostic patch

Basis: PS-RUNTIME-GUARD-SPLIT. BLE/CAN/JK paths are unchanged.

Changes:
- Keeps EU host `https://api-e.ecoflow.com`.
- Uses documented `GET /iot-open/sign/device/quota/all?sn=...` read path.
- Parses PowerStream qualified quota keys (`20_1.upperLimit`, `20_1.lowerLimit`, telemetry fields) with bare-name fallback only for compatibility.
- Adds read-only telemetry to the cloud job status: SOC, BAT voltage/current/temp, bpType, interfaceConnFlag, supplyPriority, BMS requested charge voltage/current, inverter state and Wi-Fi RSSI.
- Improves transport failure reporting with HTTP status, bytes captured and declared Content-Length where available.
- Aligns cloud write validation with the supplied PowerStream documentation: lowerLimit 1..30, upperLimit 70..100.
- Does not expose AccessKey, SecretKey, signature or signed base string.

Build status: source patch only; not compiled in this environment.
