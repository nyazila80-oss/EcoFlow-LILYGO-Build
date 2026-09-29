# AUDIT20.4.5.9.36.5 – PowerStream BLE config/UI fix

## Root causes addressed
1. The 3 s status poll rewrote `psbleenabled.checked` from backend state while the user was editing, so the checkbox could visibly clear before Save.
2. UID is intentionally write-only, but the backend previously treated an empty UID POST as a new empty UID. A later enable/disable/save could therefore erase the stored UID.
3. `NOT CONFIGURED` had no field-level diagnostics.

## Changes
- UI dirty/edit guard: polling no longer overwrites BLE Direct checkbox/address type while BLE config fields are being edited. The guard is released only after a successful save.
- Empty UID now means **keep the existing stored UID**. UID contents are never returned to the browser.
- Status adds non-secret diagnostics only: MAC valid, SN valid, UID present + length, address type valid.
- Firmware version bumped to 2.4.5.9.36.5-AUDIT20.4.5.9.36.5-PSBLE-CONFIG-FIX.

## Safety / FMEA
- Enabling still fails closed unless MAC, SN, effective UID and address type all validate.
- NVS write + immediate readback remains mandatory.
- Worker/config serialization and one-shot BLE policy unchanged.
- Supply SOC/BMS recovery guard unchanged.
- UID value is not exposed by status/API diagnostics.

## Verification in this environment
- Existing host_sim_ps_ble_lab2.py: 20,000 runs / 10,000,000 checks / 0 violations.
- Static inspection confirms the changed save path uses effectiveUid consistently for validation, NVS write/readback and runtime state.
- Full PlatformIO compile was NOT executable in this environment because the `pio`/`platformio` binary is not installed. Compile status is therefore not claimed.
