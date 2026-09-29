# 9.36.7.10 Final Deep Gate – Phase 3

## Scope
Static re-audit of the actual `/mnt/data/work9380` source tree after the project-wide, lifetime, concurrency and Web/AsyncTCP/NimBLE stress audits. Focus: security exposure introduced by NO-WEB-AUTH A/B, diagnostic observability, task/resource lifetime, and whether another simulation pass would materially reduce uncertainty.

## Confirmed findings

### F-01 HIGH – `/api/state` returns stored Wi-Fi and MQTT passwords while Web Basic Auth is disabled
Evidence: `src/web.cpp` reads `net/pass` and `mqtt/pass` from Preferences in the `/api/state` callback and serializes them as `wifi.pass` and `mqtt.pass`. `remoteAuthRequest()` currently always returns true as part of the 9.36.4 NO-WEB-AUTH diagnostic.

Impact: any host that can reach the ESP32 HTTP service can retrieve those stored credentials. This is independent of the WebUI stability fault and is a release blocker.

Recommended production fix: passwords must be write-only. `/api/state` should return presence/configuration booleans only, never secret values. The UI must preserve an existing secret when the password field is left blank.

### F-02 HIGH – persistent remote/OTA password is printed in plaintext to Serial
Evidence: `remoteAuthEnsure()` logs `[REMOTE] WebUI user=%s password=%s ...` with `sRemotePassword.c_str()`.

Impact: the OTA credential can be disclosed to anyone with serial-log access or to any later logging/collection path that captures Serial. This matters even though Web Basic Auth is disabled, because `remoteOtaAuthRequest()` still uses the same persistent secret.

Recommended production fix: never log the secret. Log only that an OTA credential exists, optionally its length or a non-reversible diagnostic identifier if truly needed.

### F-03 MEDIUM/HIGH – `/api/state` performs synchronous Preferences/NVS reads in AsyncWebServer callback
Evidence: both `net` and `mqtt` namespaces are opened/read/closed inside the GET callback.

Impact: not proven as the GUI root cause, but it increases callback work and couples flash/NVS activity to AsyncTCP request handling. Combined with dynamic String JSON construction, it is an avoidable latency/fragmentation contributor.

Recommended architectural fix after the diagnostic A/B: maintain main-loop-owned config snapshots; GET callbacks serialize snapshots only. Mutations queue work to the owner.

### F-04 HIGH diagnostic relevance – dynamic JSON remains the strongest software-side fragmentation candidate
`/api/state` reserves 2048 bytes. `/api/bms` and `/api/bms/full` reserve 4096 bytes and append many temporary `String` values. `powerStreamBleLabStatusJson()` is a very large chained dynamic String expression. These operations coexist with AsyncTCP/NimBLE allocations and are sensitive to largest-contiguous-block rather than only total free heap.

The current `/api/net/health` instrumentation is useful: free heap, largest8, min heap, BMS API inflight/max inflight, build time, minimum heap/largest observed in `/api/bms`, WS clients/cleanup, Wi-Fi event counters and loop gap are exposed.

### F-05 POSITIVE – `/api/bms` callback instrumentation now measures the right failure dimensions
The source tracks calls, inflight/max-inflight, build duration, min free heap and min largest block. This is directly useful for hardware root-cause correlation.

### F-06 POSITIVE – BMS mutation ownership has been improved
The current tree contains queued BMS operations (`PendingBmsOp`) so AsyncWebServer callbacks request operations and the main-loop-owned BMS object applies them. This reduces one important cross-context mutation class.

### F-07 POSITIVE – explicit application task creation is bounded and auditable
Explicit stacks found:
- CAN log: 2560
- CAN alert: 2560
- CAN RX: 3072
- CAN decode: 4096
- diagnostic heartbeat: 2048
- PowerStream cloud: 6144, resident once created
- PowerStream BLE one-shot/auth probe: 6144, transient

HeavyOp serialization prevents cloud and PS-BLE heavy operations from executing concurrently, but the resident cloud task stack can still coexist with a later PS-BLE worker.

### F-08 MEDIUM – source/audit version hygiene is not clean
The work tree contains audit comments with later tags (for example 9.17) while the package under review is named 9.36.7.10. This is not a runtime defect, but it weakens reproducibility. Before a release candidate, source version, FS version, package name, audit tag and manifest should be generated/verified from one source of truth.

### F-09 BUILD GATE OPEN – no PlatformIO executable in audit environment
`pio`/`platformio` is unavailable here. Therefore this audit does not claim compile, link, partition fit, IRAM/DRAM fit, library-resolution reproducibility, or binary-level success.

## FMEA delta

| Failure mode | Severity | Likelihood before HW test | Detection | Current control | Gate |
|---|---:|---:|---:|---|---|
| HTTP client reads stored Wi-Fi/MQTT password | High | High if reachable | Easy | none under NO-WEB-AUTH | Release BLOCK |
| OTA secret exposed in serial log | High | Medium | Easy | physical/log access boundary only | Release BLOCK |
| REST dynamic String fragmentation | High | Medium | Good with health counters | diagnostics + BLE guards | HW test required |
| Async callback NVS latency | Medium | Medium | Partial | none specific | refactor after A/B |
| PS-BLE pushes heap below runtime margin | High | Medium under stress | Good | 18k/9k admit + 9k/6k runtime guard | controlled HW test |
| Cloud resident task reduces later margin | Medium/High | Medium | Good | A1/A2/C1/C2 test matrix | controlled HW test |
| NimBLE callback/client lifetime race | High | Low/unknown | Partial | bounded queue, cleanup, guards | HW test required |
| Heavy cloud + PS-BLE execution overlap | High | Low | Good | HeavyOpOwner | controlled |
| stale WebSocket clients accumulate | Medium/High | Reduced | Good | cleanup all sockets + low-heap cleanup | controlled HW test |
| version/audit mismatch causes wrong artifact tested | High process risk | Medium | Easy | manual checks | fix release process |

## Root-cause status

### Not supported as sole current cause
- Web Basic Auth: disabled in current diagnostic path; therefore cannot be a necessary cause if the failure reproduces on this build.
- Old active web-server rebind: suppressed in current tree.
- Missing `/bms` websocket cleanup: corrected in current tree.

### Still credible
1. Largest-contiguous-heap collapse/fragmentation from REST/AsyncTCP plus BLE resource pressure.
2. AsyncTCP/Wi-Fi lifecycle or starvation while the main loop remains alive.
3. NimBLE/Wi-Fi coexistence/timing effects that are not reproducible in host models.
4. Cloud-resident stack lowering the margin before later PS-BLE operations.

## Required hardware evidence matrix

### A1 – fresh boot baseline
Do not invoke cloud or PS-BLE transaction. JK/NimBLE active. Observe WebUI under normal use.

### A2 – resident-cloud baseline
Run cloud function once so cloud task exists, then return to idle. Do not start PS-BLE transaction. Compare heap/largest8 and WebUI stability to A1.

### C1 – auth-only, no prior cloud creation
Fresh boot; JK app disconnected; execute PS BLE auth-only. No Storage/Supply command.

### C2 – auth-only after cloud task creation
Fresh boot; invoke cloud once; then auth-only. This isolates the resident-stack/resource-margin effect.

### D – full one-shot command
Only after A1/A2/C1/C2 are stable. Execute exactly one Storage or Supply priority command and correlate command stage with network/heap diagnostics.

## Failure capture rule
If WebUI becomes unreachable, do not immediately power-cycle. Capture serial heartbeat first. Determine:
- heartbeat alive/dead
- Wi-Fi status and IP state
- router still sees ESP32 or not
- last free heap/largest8/min heap
- BMS API min-largest/max-inflight/max-build-us
- WS client/cleanup counts
- Wi-Fi disconnect/lost-IP counters/reason
- BLE stage and heavy owner

Interpretation:
- Web dead + heartbeat alive + Wi-Fi alive + largest8 collapsed => strongest evidence for HTTP/AsyncTCP/fragmentation path.
- Web dead + Wi-Fi disconnect/lost-IP events => Wi-Fi/RF/netif path rises.
- Web dead only during C with A1/A2 stable => NimBLE/PS connect-GATT-auth coexistence rises.
- C1 stable but C2 unstable => resident cloud resource margin rises strongly.
- C stable but D fails => command/ACK/verify/cleanup delta becomes primary.

## Gate decision
- Static logic/safety gate for controlled diagnostic hardware testing: PASS WITH CONDITIONS.
- Compile/link gate: OPEN (must be performed in PlatformIO).
- Hardware stability gate: OPEN.
- Production/release security gate: BLOCKED by F-01 and F-02.

No further host-only random-state count is expected to materially close the remaining uncertainty. The next high-information action is compile/link followed by the controlled A1/A2/C1/C2/D hardware matrix. Security fixes F-01/F-02 should be applied before any production/release build; applying them before the diagnostic run would change the current A/B artifact and should be treated as a new version.
