# AUDIT20.4.5.9.36.7.8 — BLE Isolation A/B FMEA

## Objective
Determine whether the intermittent WebUI loss exists independently of JK-BLE/NimBLE. Preserve RS485 BMS, CAN, Wi-Fi, HTTP and existing safety logic.

## Design
Persistent boot-only switch in NVS namespace `jkbleiso`, key `startup` (default true).
- OFF at boot: `jkBleProxyTick()` returns before any NimBLE initialization, server/client creation, advertising or JK reconnect.
- ON at boot: historical JK BLE lifecycle remains unchanged.
- Runtime setting changes only persisted desired state. No live NimBLE deinit/reinit. Reboot is required and reported by API.
- PowerStream BLE remains fail-closed while NimBLE is disabled because its existing `jkBleProxyInitialized()` admission gate stays intact.
- No additional periodic HTTP polling was added for this diagnostic switch.

## FMEA
| Failure mode | Effect | Control |
|---|---|---|
| NVS key absent | Ambiguous behavior | default = enabled, preserving prior firmware behavior |
| NVS read fails | unexpected disabled BLE | default local value remains enabled |
| NVS write fails | requested test mode not stored | HTTP 500; no runtime state mutation claimed |
| Disable requested after NimBLE already initialized | unsafe live teardown/race | no live deinit; boot-applied state unchanged; reboot required |
| Enable requested while boot-applied OFF | unexpected live NimBLE allocation | no live init; reboot required |
| Boot-applied OFF but JK tick runs | BLE contamination of baseline | first tick gate returns before init/state machine |
| PowerStream command attempted in baseline | could contaminate A phase | existing NimBLE initialized precheck rejects fail-closed |
| RS485 BMS affected by BLE switch | invalid baseline | switch is isolated to jk_ble_proxy; BMS loop unchanged |
| CAN safety affected | regression | CAN path unchanged |
| Diagnostic endpoint itself changes load | confounded baseline | manual endpoint only; no new periodic poll |
| Concurrent web read/write of switch | torn state | desired/applied values atomic; NVS write synchronous; applied state immutable until reboot |
| Power loss during preference write | setting uncertain | Preferences/NVS transactional behavior; next boot defaults enabled if key unavailable |

## Test phases
A: boot with JK BLE/NimBLE OFF, PowerStream BLE cannot run. RS485 BMS + Wi-Fi/WebUI only.
B: store ON and reboot. JK BLE/NimBLE lifecycle enabled; PowerStream command still not sent.
C: after A/B comparison, PowerStream BLE one-shot can be tested separately.

## Host model
`host_sim_ble_isolation_ab.py`: 2,000,000 randomized persisted/runtime/reboot state sequences, 0 invariant violations.
Existing regression models rerun: PS BLE lab 10,000,000 checks / 0; resource gate 10,000,000 / 0; BLE owner handshake 6,000,000 / 0.

## Hardware boundary
Host tests cannot prove ESP32 radio coexistence, AsyncTCP/LwIP behavior, RF interference, heap fragmentation, or timing under real FreeRTOS scheduling. Hardware A/B is required.
