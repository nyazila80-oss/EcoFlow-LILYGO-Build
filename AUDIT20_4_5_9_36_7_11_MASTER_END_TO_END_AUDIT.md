# MASTER END-TO-END AUDIT — 9.36.7.11

Scope: complete current project tree `/mnt/data/work9381`, from boot/config through RS485/BMS, CAN/TWAI/EcoFlow emulation, low-SOC/SOH guards, JK BLE proxy, PowerStream BLE one-shot/auth-only, PowerStream cloud API, Wi-Fi/NTP/MQTT, AsyncWebServer/WebSockets, OTA/SPIFFS, NVS/config ownership, task/heap/concurrency, UI/filesystem and host simulations.

## Inventory / release identity
- 326 files in working tree, ~1.9 MiB total.
- `src/`, `include/`, `data/`: 9,189 lines.
- FW_VERSION = `2.4.5.9.36.7.11-AUDIT20.4.5.9.36.7.11-SECURITY-HARDENED-DIAG`.
- `data/fs_version.txt` matches FW_VERSION exactly.
- ZIP SHA-256: `fa48ff3483f031eba01764254ed8fffe3c8b71d8f3da49b213026194aa84b37b`.
- PlatformIO is not installed in the audit environment; ESP32 compile/link remains an external hard gate.

## Boot and lifecycle
Verified boot order: serial -> config/MQTT identity -> core config -> PS BLE config -> PS cloud config -> BMS -> SPIFFS -> Wi-Fi diagnostics/config -> EcoFlow message init -> TWAI driver/tasks -> NTP -> Web/OTA/static routes -> HTTP listener -> diagnostic heartbeat. Main loop retains OTA, Wi-Fi recovery, NTP, MQTT, config apply, BMS, low-SOC guard, JK BLE, PS BLE tick, web tick, CAN sequencer and callback recorder with `delay(1)` scheduler handoff.

No intentional `server.end()/begin()` rebind remains on STA/IP recovery; legacy rebind requests are consumed while listener is retained.

## RS485 / BMS
- BMS UART initialized at configured RS485 baud; bounded parsing/snapshot paths remain.
- BMS writes originating from web are deferred/owned rather than arbitrary direct mutation from AsyncTCP callbacks where hardened paths apply.
- Snapshot/short-lock design and previous RS485 timing model remain consistent.
- Host RS485 timing model: valid=32,288; timeout=17,712; mixed_reject=0; false_accept=0; boundary_ok=17,712.
- Remaining hardware gate: electrical timing/noise and actual Felicity response behavior cannot be proven by host simulation.

## CAN / TWAI / EcoFlow protocol
- EcoFlow message/TX serialization state is initialized before CAN tasks start.
- CAN RX, decode and TX paths retain bounded DLC/copy handling and fail-closed gates.
- Bus-off recovery model: 10,000,000 checks, 0 violations.
- Loop-stall CAN fail-closed model: 10,000,000 checks, 0 violations.
- CAN TX boundary model: 1,000,000 messages / 18,574,423 fragment checks / 866,854 modeled aborts / 0 violations.
- Physical CAN interoperability, arbitration timing and real PowerStream behavior remain hardware gates.

## Low-SOC/SOH and battery safety
- Guard configuration uses atomic/snapshot ownership paths.
- Guard application remains in main-loop ownership before CAN TX sequencing.
- No audit change reintroduced automatic PowerStream priority control.
- Hardware validation is still required for actual charge/discharge inhibition behavior at thresholds.

## JK BLE proxy
- JK proxy remains distinct from PowerStream BLE and future DELTA 2 emulation.
- Bounded bridge queues, age/backpressure/session epoch and resource ownership guards remain.
- Shared NimBLE admission and JK-app coexistence safety are retained.
- Hardware-only residual: NimBLE callback/disconnect timing and RF coexistence.

## PowerStream BLE
- Real PS one-shot path remains separate from JK proxy.
- AUTH_ONLY path exits after Connect -> GATT -> Subscribe -> Auth and before `supplyFrame()` / priority write.
- Common cleanup resets transaction depth, cleans client state, releases AUX/heavy owner and deletes worker.
- Admission/runtime heap guards remain two-stage.
- Coexistence model: 3,000,000 states / 0 violations.
- BLE owner: 6,000,000 checks / 0 violations.
- Resource gate: 10,000,000 steps / 0 violations.
- PS BLE memory lifecycle: 2,000,000 runs / admitted 976,626 / runtime blocks 103,741 / 0 invariant violations.
- Residual hardware gate: real GATT/auth timing, disconnect callback timing, controller memory behavior and physical command observation.

## PowerStream cloud API
- Recursive API mutex, static job mutex and atomic job state are present.
- Heavy operation ownership serializes cloud heavy work against PS BLE heavy work.
- Cloud worker uses 6,144-byte stack and, once created, remains a resident resource; this must be included in A1/A2/C1/C2 memory comparisons.
- Network/TLS/cloud service behavior remains an external/hardware/network gate.

## Wi-Fi / network / MQTT / NTP
- Wi-Fi event diagnostics, reconnect/recovery and AP fallback remain.
- Active HTTP listener rebind was intentionally removed to avoid racing live AsyncTCP clients.
- MQTT config is deferred/verified in hardened paths; NTP/MQTT remain tick-driven.
- Web/Wi-Fi lifecycle model: 3,000,000 states / 0 violations; model also identifies old live-client rebind exposure and low-heap pressure states.
- Residual: router/RF/LwIP/AsyncTCP timing can only be established on hardware.

## WebUI / AsyncTCP / WebSockets
- Central WS cleanup and bounded low-heap cleanup remain.
- `/bms` WS uses bounded stack JSON then `makeBuffer()` fail-closed behavior.
- Dynamic REST JSON remains a major diagnostic risk: `/api/state` reserves ~2 KiB; `/api/bms` and `/api/bms/full` reserve ~4 KiB plus temporary Strings; PS BLE status also performs substantial dynamic concatenation.
- Combined Web+AsyncTCP+heap+NimBLE stress model: 500,000 runs, 0 post-guard invariant violations; 65,972 PS admissions, 8,175 runtime aborts, 26,646 modeled web allocation failures, 1,206 fail-closed WS drops; largest-block median 9,279 B, p10 3,392 B.
- This does not prove an ESP32 heap leak; it confirms that largest-contiguous-block pressure is a credible failure mechanism requiring hardware telemetry.

## Authentication / credentials / security
9.36.7.11 fixes the two confirmed diagnostic-release security defects:
- remote/OTA password is no longer printed in clear text; log is redacted.
- `/api/state` no longer returns Wi-Fi or MQTT passwords, only `pass_set` booleans.
- UI password fields are write-only; blank preserves an existing credential.
- WebUI Basic Auth remains deliberately disabled for the controlled A/B diagnostic; OTA remains authenticated.
- Same-origin checks remain on mutating browser/API operations.
- Important limitation: because normal WebUI Basic Auth is disabled, this diagnostic build should remain on a trusted/private network and must not be exposed directly to the Internet.

## OTA / SPIFFS / partitioning
- Firmware and filesystem HTTP OTA require OTA auth and same-origin mutation guard.
- Firmware upload validates `.bin`; filesystem upload validates `spiffs.bin`.
- Failed FS OTA attempts remount SPIFFS where appropriate.
- Custom partition table provides dual ~1.75 MiB OTA app slots, 384 KiB SPIFFS and 64 KiB coredump.
- First migration to custom partition table still requires USB; OTA cannot replace partition table.
- FW/FS version strings match in the current tree.

## Memory / task / concurrency map
Explicit application task stacks include CAN log 2,560 B, CAN alert 2,560 B, CAN RX 3,072 B, CAN decode 4,096 B, diagnostic heartbeat 2,048 B, cloud worker 6,144 B resident after creation, PS BLE worker 6,144 B temporary. This excludes Wi-Fi/LwIP/AsyncTCP/NimBLE system tasks/objects and dynamic HTTP/GATT allocations.

No confirmed cyclic lock-order deadlock was found in the audited application lock graph. Critical sections remain short and do not intentionally wrap network/NVS/GATT blocking work. HeavyOpOwner prevents simultaneous heavy cloud/PS-BLE operations, but the resident cloud task still consumes memory after creation.

Worst-case lifetime model: 2,000,000 runs / 0 invariant violations / 159,866 PS admitted / 11,742 runtime fail-closed / 28,883 heavy-op overlaps blocked. The older model had zero web-pressure events, which is why the dedicated web/heap stress model is the stronger evidence for that failure class.

## Static safety scan
- No obvious unbounded `strcpy`/`strcat`/`sprintf` family use was found in project source.
- Fixed-size `memcpy` sites inspected are paired with protocol/DLC/length bounds in the current hardened paths; no deterministic fixed-buffer overflow was identified in this pass.
- No TODO/FIXME marker identified an unresolved production path; `Update.abort()` uses are intentional OTA failure handling.
- Python simulation sources compile syntactically (`compileall` passed).

## Simulation evidence — valid current models rerun
PASS:
- staged JK/PS coexistence: 3,000,000 / 0
- BLE owner: 6,000,000 / 0
- resource gate: 10,000,000 / 0
- PS BLE memory lifecycle: 2,000,000 / 0
- CAN bus-off: 10,000,000 / 0
- loop-stall CAN gate: 10,000,000 / 0
- config single-owner: 2,000,000 steps / 0
- web/Wi-Fi lifecycle: 3,000,000 / 0
- web+AsyncTCP+heap+NimBLE stress: 500,000 / 0 post-guard
- worst-case lifetime: 2,000,000 / 0
- RS485 timing: false_accept=0, mixed_reject=0
- CAN TX boundary: 18,574,423 fragment checks / 0

Not counted as current PASS evidence:
- `host_sim_v24_final_audit.py` fails stale static expectations (version/older source-shape assumptions).
- `host_sim_final_regression.py` fails its historical FW-version assertion.
- very long notify/auto-FSM models timed out in this audit invocation and are not claimed as fresh PASS results here.
These are test-harness maintenance issues unless a current semantic assertion is separately shown to fail; they must not be presented as current release PASSes.

## Remaining findings / risk register
P1 — Hardware compile/link gate: PlatformIO unavailable in audit environment. Clean local build is mandatory before flash.
P1 — Real ESP32 contiguous heap / AsyncTCP / NimBLE coexistence: strongest unresolved stability risk. Measure free heap AND largest8/min heap during A1/A2/C1/C2/D.
P1 — Real hardware BLE/GATT/disconnect timing and PowerStream command observation remain unproven.
P2 — Dynamic REST String construction is still a fragmentation/latency candidate; do not rewrite before baseline hardware capture unless build/runtime evidence requires it.
P2 — Cloud worker lifetime permanently changes post-first-use memory baseline; explicitly test before/after creation.
P2 — Normal WebUI is unauthenticated by design in this diagnostic A/B build; trusted LAN/VPN only.
P3 — Dependency reproducibility: `ESPAsyncWebServer @ ^3.7.10` and unpinned `espressif32` platform permit dependency drift. Freeze resolved versions for a final production release after diagnosis.
P3 — Historical simulation scripts contain stale version/source-shape assertions; update them before using a single all-tests release gate.
P3 — Historical audit comments/tags from older versions remain in source; harmless at runtime but should be normalized for final traceability.

## Final audit verdict
9.36.7.11 is internally consistent enough to proceed to a controlled diagnostic hardware build/test, subject to a successful clean PlatformIO compile/link. No newly discovered deterministic defect in RS485, CAN/TWAI, low-SOC guard, JK BLE ownership, PS BLE AUTH_ONLY boundary, heavy-operation serialization, OTA flow or credential redaction blocks that diagnostic test.

It is NOT yet a production release. The remaining decisive evidence must come from the real ESP32: compile/link, boot, long-run WebUI/heap behavior, Wi-Fi/AsyncTCP behavior, NimBLE coexistence, RS485/CAN physical behavior and PowerStream GATT/command observation. Do not erase NVS for the diagnostic comparison. Upload firmware + filesystem because data assets/version changed.

Recommended hardware gate sequence: Clean -> Build -> firmware upload -> filesystem upload -> normal reboot; then A1 (fresh boot, cloud worker never created), A2 (cloud worker created once), C1 (PS auth-only before cloud-worker lifetime where practical), C2 (auth-only after cloud-worker creation), D (single priority command only after earlier gates are stable). On any WebUI failure, do not immediately power-cycle: preserve serial heartbeat, Wi-Fi event counters, free heap, largest8/min heap, BMS API latency/inflight, WS client/cleanup counts, BLE stage and heavy-owner state.
