# TLS Memory Isolation Diagnostic — follow-up

Basis: 9.36.7.11 OPENAPI READONLY CLOUD RTC TRACE GET ERROR DIAG.

## Reason
PC reference test reached EcoFlow successfully: device/list and quota/all returned HTTP 200 / EcoFlow code 0. ESP32 hardware test failed before HTTP response with TLS -32512 / SSL memory allocation failed.

## Change
Read-only instrumentation only. No API URL, keys, signatures, CA policy, CAN, JK-BMS, BLE behavior, NVS or cloud write policy changed.

/api/powerstream/job now reports free heap and largest 8-bit block at six TLS stages:
- tls_*_client: after WiFiClientSecure construction
- tls_*_ca: after setCACert
- tls_*_begin_pre: immediately before HTTPClient.begin
- tls_*_begin_post: immediately after successful begin
- tls_*_get_pre: immediately before GET
- tls_*_get_post: immediately after GET returns

## Safety
TLS remains fail-closed with ECOFLOW_CA_BUNDLE. No setInsecure fallback. Cloud writes remain disabled.

## Build gate
Not executed in this ChatGPT runtime because PlatformIO is not installed here. Run Full Clean + Build in the user's established PlatformIO environment before flashing.

## Hardware test
After successful build/OTA, run exactly one Connection Test and capture /api/powerstream/job plus /api/net/health. Compare largest8 across the six TLS stages. Do not repeat tests until the first trace is captured.
