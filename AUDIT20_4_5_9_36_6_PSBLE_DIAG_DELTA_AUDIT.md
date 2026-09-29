# AUDIT20.4.5.9.36.6 — PowerStream BLE diagnostics + DELTA identity audit

## Finding: 603134845005019-00 is not a DELTA 2 emulator
Source inspection shows this advertiser is created by `src/jk_ble_proxy.cpp`:
- `JK_PROXY_NAME = "603134845005019-00"`
- GATT service `FFE0`, characteristic `FFE1`
- the server bridges a phone-side connection to the real JK-BMS BLE link.

Therefore Android/LightBlue visibility of this device proves the JK-BLE proxy is advertising. It does not prove an EcoFlow DELTA 2 peripheral exists. The code intentionally keeps this identity/protocol unchanged in 9.36.6 because replacing it would break the JK proxy path.

Public reverse-engineering references identify DELTA 2 by an R33/R331-family serial and document EcoFlow BLE protocol/GATT distinct from the JK FFE0/FFE1 bridge. A true DELTA 2 peripheral emulator must be implemented as a separate, protocol-correct feature and must not silently replace the safety-critical JK proxy.

## PowerStream BLE Direct diagnostics
9.36.6 preserves the one-shot/no-auto-reconnect design and adds non-secret stage telemetry:
- physical BLE connect reached
- service 0001 found
- write characteristic 0002 found
- notify characteristic 0003 found
- notify subscription succeeded
- auth-status frame transmitted
- auto-auth frame transmitted
- raw auth response byte, when received

Authentication rejection now records the exact response byte (`0xNN`) instead of only `authentication rejected`. No UID, derived MD5, AES key, IV, or packet payload is returned by the status API.

## Safety invariants retained
- no scan
- no automatic reconnect
- no automatic SOC control
- JK core link must remain healthy
- auxiliary BLE slot/resource gate remains mandatory
- Supply remains blocked by SOC/BMS recovery guard
- heap guards and cleanup path unchanged
