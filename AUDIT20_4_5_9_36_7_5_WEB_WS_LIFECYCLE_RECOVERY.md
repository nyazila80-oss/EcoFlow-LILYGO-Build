# AUDIT20.4.5.9.36.7.5 — WEB/WS LIFECYCLE + RECOVERY

## Trigger
Hardware on 9.36.7.2: WebUI at STA IP becomes unreachable after runtime and only returns after board power-cycle. Earlier STA/IP rebind did not eliminate the fault.

## Source finding
`webTick()` called `ws_flush_ring()` only for `wsLog` and `wsDebug`. Cleanup was embedded inside `ws_flush_ring()` behind a function-static shared `lastCleanup`. Therefore only the first eligible ring websocket could own the cleanup cadence. More importantly, `wsBms` (the dashboard telemetry websocket) never passed through `cleanupClients()` at all; it was only pushed/pinged. Repeated browser reconnects can therefore retain stale AsyncWebSocket/AsyncTCP client state and create heap/socket pressure. This is a concrete lifecycle defect and matches the observed pattern better than an STA/DHCP-only theory.

## Fix
- Removed websocket cleanup from per-ring flush path.
- Added one main-loop-owned cleanup cadence every 1000 ms for ALL endpoints: `/log`, `/bms`, `/debug`.
- Added one additional bounded cleanup pass under heap pressure (<14 kB free or <7 kB largest block). No reboot and no periodic server rebind.
- Added lifecycle counters: WS client counts, cleanup runs, low-heap cleanup count, webTick last/max loop gap, ESP minimum free heap.
- `/api/net/health` remains lightweight/no-store and exposes these fields.
- PowerStream page polls net health and appends the lifecycle values to HTTP diagnostics.

## FMEA
1. Dead BMS browser/socket client: cleanup <=1 s; stale state is reclaimable.
2. Dead log/debug client: same global cleanup path; no shared-timer starvation.
3. No clients: cleanup is bounded and harmless; no allocations intentionally introduced.
4. Heap pressure: extra cleanup only; no forced reboot, no Wi-Fi credential mutation.
5. Wi-Fi loss/recovery: existing STA recovery and transition rebind retained.
6. BLE/PowerStream heavy operation: no server end/begin is triggered by this change; Resource Gate unchanged.
7. Main-loop stall: last/max webTick gap exposes starvation rather than silently masking it.
8. HTTP server itself dead while STA healthy: diagnostics may become unreachable; serial ALIVE + FritzBox/ping remain the hardware discriminator. No claim that WS cleanup proves all AsyncTCP failure modes fixed.

## Simulation / regression
- `host_sim_web_ws_lifecycle.py`: 2,000,000 randomized reconnect/heap states; 0 model violations; 70,105 modeled old-pressure cases reclaimed by all-endpoint cleanup.
- `host_sim_ps_ble_memory_lifecycle.py`: 2,000,000 states; 0 violations.
- `host_sim_resource_gate.py`: 10,000,000 steps; 0 violations.
- `host_sim_ble_owner_handshake.py`: 6,000,000 checks; 0 violations.
- `host_sim_ps_ble_lab2.py`: 10,000,000 checks; 0 violations.
- `host_sim_ps_ble_arbiter.py`: 80,000,000 checks; 0 violations.
- `host_sim_final_regression.py`: 12/12 static checks; CAN/EcoFlow/JK randomized regressions passed. Harness version predicate updated from old 9.36.7 literal to 9.36.7.5; no production logic changed for that harness update.

## Scope boundaries
No changes to CAN protocol, RS485 parser, BMS safety snapshot, SOC/SoH guards, PowerStream GATT/auth/commands, BLE Resource Gate, OTA protection, or Wi-Fi credentials. 9.36.7.4 BLE memory lifecycle instrumentation is retained.

## Verification boundary
Source audit and host models cannot reproduce the ESP32 lwIP/AsyncTCP radio/runtime stack. Hardware soak test is mandatory. If UI fails again, do not power-cycle immediately: check FritzBox association/ping and Serial `[ALIVE]`; this separates STA loss, HTTP/AsyncTCP failure, and whole-loop starvation.
