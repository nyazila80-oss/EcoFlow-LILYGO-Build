# AUDIT 20.4.5.9.2 — PS PRIORITY SHARED BLE HARDENED

## Architecture decision
PowerStream BLE reuses the single NimBLEDevice instance initialized by the proven JK BLE proxy. There is exactly one NimBLEDevice::init() in src/. PowerStream does not scan and does not initialize/deinitialize the BLE stack.

## Connection budget
MYNEWT_VAL_BLE_MAX_CONNECTIONS remains 2. A PowerStream one-shot is admitted only when the real JK-BMS link is connected and the virtual JK app/client is disconnected. Thus the intended active set is JK-BMS + PowerStream = 2. If the JK app is connected, the PS operation is rejected rather than increasing the connection budget to 3.

## Callback rule reused from JK solution
PowerStream notification callback only copies <=244 bytes into a fixed 4-slot queue. AES decrypt, protobuf parsing, authentication state interpretation and heartbeat field-50 parsing run in the PS worker task. No String, Serial, crypto, GATT write or dynamic allocation is performed in the notification callback.

## Radio / WiFi containment
No BLE scan. No automatic reconnect. One-shot only. Requires 5 s stable WiFi before admission. Failed operations enter cooldown and never self-retry.

## Core-link preservation
A PS operation is rejected if JK/NimBLE is not initialized, if the real JK-BMS BLE link is down, or if a JK app is connected. PS failure never intentionally disconnects the JK client and never reinitializes NimBLE.

## Safety regression
src/can.cpp byte-identical to 20.4.5.8.
src/low_soc_guard.cpp byte-identical to 20.4.5.8.
Therefore the existing BMS-stale CAN-TX fail-closed path was not modified.

## Simulations
Existing PS state/admission simulation: 20,000 runs / 10,000,000 checks / 0 violations.
New shared-BLE connection-budget/admission fuzz: 30,000 runs / 18,000,000 checks / 0 violations.
These are host logic simulations, not RF, heap allocator, or hardware validation.

## Remaining gates
1. Real PlatformIO compile against NimBLE-Arduino 2.5.1.
2. Hardware test: WiFi/WebUI responsiveness while PS one-shot connects/authenticates.
3. Verify JK-BMS link remains uninterrupted during PS one-shot.
4. Verify Storage Priority heartbeat confirmation and actual JK current behavior.
5. Verify PV charging remains possible while Storage Priority is active.
