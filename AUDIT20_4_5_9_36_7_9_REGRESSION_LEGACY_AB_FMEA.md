# AUDIT20.4.5.9.36.7.9 — Regression Legacy A/B FMEA

## Objective
Test the user's historical observation that JK-BLE + JK app + WebUI was stable before the 20.4.5.8-era regression, without falsely treating JK-BLE itself as the primary suspect.

## A/B definition
NORMAL: current runtime behavior.
LEGACY-LIKE: JK-BLE/NimBLE remains available; RS485, CAN safety logic, Wi-Fi, WebUI, OTA and serial heartbeat remain active. PowerStream BLE runtime tick is isolated, manual PowerStream BLE command is rejected, and the unused `/bms` WebSocket periodic push is isolated. Configuration is persisted and applied only at boot.

This is intentionally called **legacy-like**, not 20.4.5.7, because a complete byte-for-byte 20.4.5.7 source tree is not present in this workspace.

## FMEA
| Failure mode | Effect | Control |
|---|---|---|
| JK-BLE accidentally disabled | invalid historical comparison | legacy mode does not alter JK startup setting; UI states JK retained |
| PowerStream BLE worker starts during baseline | contaminates A/B | loop tick suppressed and command endpoint returns HTTP 423 |
| live teardown races NimBLE | crash/heap corruption | mode boot-applied only; no live deinit |
| `/bms` WS push adds allocator/TCP load | masks baseline | periodic push suppressed in legacy-like mode; cleanup remains active |
| CAN/RS485 safety path altered | unsafe/confounded test | no changes to BMS loop, low-SOC guard, CAN sequencer or CAN tasks |
| NVS write fails | requested mode not applied | POST returns 500; applied state changes only after reboot |
| user mistakes mode for exact old firmware | invalid conclusion | UI and audit explicitly say legacy-like, not exact reconstruction |
| stale WebSocket clients accumulate | heap pressure | cleanupClients remains active in both modes |
| loss of diagnostics hides failure | poor evidence | serial heartbeat, net health and REST diagnostics remain active |

## Simulation
`host_sim_regression_legacy_ab_9379.py`: 3,000,000 randomized states, 0 invariant violations.
Existing resource-gate, BLE-owner and BLE-memory lifecycle simulations were rerun unchanged.

## Static audit assertions
- JK BLE tick remains in main loop.
- Legacy-like mode only gates PowerStream BLE tick and `/bms` periodic WS push.
- PowerStream manual command is fail-closed with HTTP 423 in legacy-like mode.
- No live NimBLE deinit added.
- Firmware and filesystem version markers must match before release packaging.

## Interpretation
If LEGACY-LIKE is stable while NORMAL reproduces the GUI failure, the regression is more likely in a later auxiliary runtime/load path than in JK-BLE itself. If both fail similarly, focus returns to common paths: HTTP/AsyncTCP/LwIP, heap fragmentation, Wi-Fi lifecycle, shared diagnostics, or BMS/web request behavior. This test cannot by itself identify the exact offending commit.
