# AUDIT20.4.5 – 9.36.7.11 Security-Hardened Diagnostic Gate

## Scope
Derived from the audited 9.36.7.10 diagnostic tree. This revision intentionally changes only credential exposure/handling plus version/boot identification. BLE/CAN/RS485/PowerStream transaction logic and the WebUI heap diagnostic architecture are otherwise retained for A/B comparability.

## Changes
1. Serial credential disclosure removed. `remoteAuthEnsure()` now logs `<redacted>` and only a boolean configured state; the persistent OTA credential itself is never printed.
2. `/api/state` no longer returns stored Wi-Fi or MQTT passwords. It returns only `pass_set` booleans.
3. `index.html` no longer hydrates password inputs from `/api/state`; password fields are write-only.
4. To avoid erasing credentials when the user saves unrelated settings, an empty Wi-Fi/MQTT password input preserves the already stored password.
5. FW and filesystem versions advanced together to 9.36.7.11.

## Important semantic limitation
Because blank now means "keep existing" when a stored password exists, this diagnostic build cannot intentionally clear an existing Wi-Fi/MQTT password merely by submitting an empty password field. A future production UI should provide an explicit "clear/change credential" action if that behavior is required. This is preferable to accidental credential erasure in the diagnostic build.

## Static security checks
- No `password=%s` logging remains under `src/`.
- No `jsonEscape(statePass)` / `jsonEscape(mPass)` response serialization remains.
- Remaining `getString("pass", ...)` sites are persistence/use/readback paths, not response disclosure paths.
- Web Basic Auth remains disabled exactly as in the diagnostic A/B baseline; OTA password protection is not removed.

## Regression / model reruns
- staged JK/PowerStream coexistence: 3,000,000 states, 0 violations
- Web/Wi-Fi lifecycle: 3,000,000 states, 0 violations
- Resource gate: 10,000,000 steps, 0 violations
- Web+AsyncTCP+heap+NimBLE stress: 500,000 runs, 0 post-guard invariant violations; 8,175 modeled runtime fail-closed aborts; 26,646 modeled web allocation failures; 1,206 modeled WS fail-closed drops
- Worst-case lifetime: 2,000,000 runs, 0 invariant violations; 11,742 modeled PS runtime fail-closed events
- NimBLE notify race: 10,000,000 events, 0 modeled invalid notifications
- Resource gate lifetime: 10,000,000 checks, 0 violations

These host simulations validate only their modeled invariants. They do not establish ESP32 compile/link success, real heap fragmentation, RF coexistence, AsyncTCP behavior, or hardware stability.

## FMEA delta
| Failure mode | Previous state | 9.36.7.11 control | Residual risk |
|---|---|---|---|
| OTA/Web credential printed on UART | Confirmed | Secret redacted; only configured boolean logged | Physical/serial access still exposes other diagnostics, not secret |
| Wi-Fi password returned by `/api/state` | Confirmed | Secret removed; `pass_set` only | LAN endpoint still exposes non-secret configuration |
| MQTT password returned by `/api/state` | Confirmed | Secret removed; `pass_set` only | Same |
| Blank UI field erases stored credential | Would be introduced by naive redaction | Backend preserves stored secret on blank | Cannot intentionally clear existing secret with blank field |
| Security hardening changes BLE root-cause path | Risk | No BLE/CAN/RS485 transaction logic changed | Hardware A/B still required |
| Web heap fragmentation | Open | Diagnostics retained; no broad web rewrite | Still primary hardware investigation target |

## Gate
- Controlled hardware diagnostic: READY AFTER a clean PlatformIO compile/link.
- Production release: NOT YET. Hardware stability remains unverified and the blank-means-keep credential UX is diagnostic-oriented.
- PlatformIO compile/link: NOT VERIFIED in this audit environment because PlatformIO is unavailable.

## Recommended hardware sequence
Clean -> Build -> Firmware Upload -> Filesystem Upload. Do not erase flash. Then A1 (fresh boot/no cloud worker), A2 (cloud worker resident), C1 (auth-only without prior cloud worker on a fresh boot), C2 (auth-only after cloud worker resident), and only then D (one-shot command). Capture free heap, largest block, minimum heap, BMS API latency/inflight, Wi-Fi events, WS clients, BLE stage, and serial heartbeat. Do not power-cycle immediately after a WebUI failure; preserve evidence first.
