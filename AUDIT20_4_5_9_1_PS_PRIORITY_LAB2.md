# AUDIT20.4.5.9.1 – PS-PRIORITY-LAB2-HARDENED

## Scope
Hardening of the manual PowerStream BLE priority experiment. No automatic SOC control.
The existing CAN stale fail-closed and low-SOC guard source files are unchanged from 20.4.5.9/20.4.5.8 baseline.

## Main changes
- Removed periodic 10 s PowerStream reconnect loop.
- No BLE scan: direct connection to configured PowerStream MAC only.
- Manual request starts at most one one-shot worker task.
- Synchronous connect/GATT/auth waits moved out of Arduino main loop.
- Worker is low priority and pinned to core 1; waits use vTaskDelay/yield.
- Source-reference auth timing restored: 300 ms after subscribe, 400 ms between auth-status and auto-auth, auth timeout 10 s.
- Heap + largest-free-block + heap-integrity admission guards.
- WiFi must be continuously connected for 5 s before a manual PowerStream operation starts.
- 30 s cooldown after failed operation; no automatic retry.
- PowerStream client is disconnected and deleted after each operation to release transient GATT/client memory.
- Callback no longer clears GATT pointers asynchronously; link state is atomic and worker owns pointer lifecycle.
- Manual command is only considered CONFIRMED after heartbeat field 50 equals requested mode.
- Optional BLE address type stored (0 public, 1 random); public remains default/reference behavior.

## FMEA highlights
1. PowerStream absent / wrong MAC -> bounded connect timeout -> FAILED -> cleanup -> 30 s cooldown. Main loop continues.
2. Authentication rejected/timeout -> cleanup/cooldown; no repeated reconnect storm.
3. Low/fragmented heap -> operation rejected before worker allocation or before command.
4. Link loss during auth/write -> atomic link-down detected; pointers are not invalidated from callback; worker cleans up.
5. Duplicate web requests -> atomic worker admission permits only one operation.
6. WiFi associating/unstable -> request rejected until 5 s continuous STA connectivity.
7. Heartbeat/readback missing -> command is NOT declared successful; VERIFY timeout -> FAILED.
8. PS BLE disabled -> no PS client, no PS reconnect, no background PS radio activity.
9. BMS stale -> existing CAN fail-closed path unchanged.
10. PowerStream BLE failure cannot intentionally stop CAN/RS485/WiFi or reboot the device.

## Static checks
- `src/can.cpp`: byte-identical to LAB baseline.
- `src/low_soc_guard.cpp`: byte-identical to LAB baseline.
- PowerStream module: no scan call, no periodic retry constant, no Arduino `delay()`; worker waits are RTOS yielding waits.
- Balanced source brace/parenthesis counts checked.

## Host simulation
`host_sim_ps_ble_lab2.py`: 20,000 randomized runs × 500 steps = 10,000,000 policy checks, 0 invariant violations.
This validates the abstract one-shot/cooldown/no-auto-start state policy only. It does not simulate RF, NimBLE, EcoFlow hardware, timing, heap allocator behavior, or the actual PowerStream protocol.

## External protocol cross-check
Just-Zuul V2.6.3 reference uses PowerStream UUIDs 00000001/02/03, public BLE address, auth-status 0x35/0x89, auto-auth 0x35/0x86, and verified BLE supply-priority command cmd_set 0x14 / cmd_id 0x82. Heartbeat field 50 is supply mode.

## Remaining blockers before OTA
- No PlatformIO compiler is installed in the current environment; this release is NOT compile-verified here.
- Actual coexistence with the existing JK BLE client/server + WiFi must be hardware-tested.
- Heap thresholds are conservative policy values, not hardware-proven thresholds.
- Physical meaning of Storage Priority for the user's exact PowerStream/battery arrangement must be verified by JK current and charging behavior.
