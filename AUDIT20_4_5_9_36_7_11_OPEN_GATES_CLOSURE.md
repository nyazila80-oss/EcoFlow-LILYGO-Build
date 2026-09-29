# 9.36.7.11 — Open Gates Closure Addendum

## Scope
Closure review for the four explicitly open items after the master end-to-end audit: ESP32 heap/largest-block observability, two stale host regression tests, dependency reproducibility, and NO-WEB-AUTH diagnostic posture.

## 1. Heap / largest contiguous block
Status: SOFTWARE OBSERVABILITY SUFFICIENT; HARDWARE VALIDATION STILL REQUIRED.

The current diagnostic tree already exposes free heap, minimum heap, largest 8-bit-capable block, BMS API minimum heap/largest block, API timing/inflight counters, WebSocket client/cleanup counters, Wi-Fi events, BLE stages and task/stack diagnostics. Adding another watcher before hardware validation would change the baseline without closing the hardware-only uncertainty. Therefore no firmware change was made for this item.

Residual gate: observe these metrics on real ESP32 during A1/A2/C1/C2/D. Host simulation cannot prove real allocator fragmentation, AsyncTCP/LwIP/NimBLE timing or RF coexistence.

## 2. Stale host tests
Status: CLOSED.

Updated `host_sim_v24_final_audit.py` to the current 9.36.7.11 version and current web snapshot architecture. Updated `host_sim_final_regression.py` version assertion to 9.36.7.11 while preserving its protocol, CAN, RS485, JK and queue/ring invariants.

Fresh results:
- host_sim_v24_final_audit.py: PASS; 2,000,000 modeled operations; 0 violations; all 7 static checks true.
- host_sim_final_regression.py: PASS; 20 seeds; 12 static checks; 40,000 valid EcoFlow frames; 40,000 corrupted EcoFlow rejects; 40,000 CAN reassemblies; 40,000 each drop/duplicate/trailing rejects; 40,000 JK valid; 40,000 JK corruption rejects; 400,000 FIFO operations; 240,000 ring operations.

These tests are again valid current-tree gates. They remain host models, not hardware proof.

## 3. Dependency pinning
Status: DEFERRED UNTIL FIRST SUCCESSFUL LOCAL PLATFORMIO RESOLUTION; DO NOT GUESS.

Current platformio.ini intentionally contains `platform = espressif32`, `ESPAsyncWebServer @ ^3.7.10`, `PubSubClient @ ^2.8`, and exact `NimBLE-Arduino @ 2.5.1`. PlatformIO is unavailable in this audit environment, so the actually resolved platform/framework/AsyncTCP/ESPAsyncWebServer/PubSubClient versions cannot be truthfully frozen here.

Closure procedure after the first successful clean local build: record the resolved package/library versions from PlatformIO, then pin exactly those versions in a release-candidate branch and rebuild. Do not alter the 9.36.7.11 diagnostic baseline before that measurement.

## 4. NO-WEB-AUTH
Status: INTENTIONAL DIAGNOSTIC CONDITION, NOT A PRODUCTION CLOSURE.

9.36.7.11 deliberately keeps WebUI Basic Auth removed to preserve the authentication A/B isolation. Credential exfiltration findings from 9.36.7.10 were separately hardened: Wi-Fi/MQTT secrets are not returned by `/api/state`, and the OTA password is redacted from serial output. OTA remains password protected.

Production release gate: after hardware root-cause validation, reintroduce a low-allocation web-auth design and rerun the full web/heap/coexistence regression. Until then, use 9.36.7.11 only on a trusted LAN/VPN with no port-80 Internet exposure.

## Gate conclusion
Two items are now closed in software/test infrastructure: stale tests and credential hardening. Heap observability is sufficient but real-hardware behavior is inherently still open. Dependency pinning requires the resolved versions from a successful local PlatformIO build. NO-WEB-AUTH remains deliberately open for diagnostic validity and must be closed only in the later production RC.
