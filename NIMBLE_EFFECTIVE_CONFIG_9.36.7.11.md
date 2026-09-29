# NimBLE effective configuration correction — 2026-09-25

Review of the preceding BUILD-PINNED-DIAG found that its `-DMYNEWT_VAL_BLE_MAX_CONNECTIONS=2` and `-DMYNEWT_VAL_BLE_ROLE_OBSERVER=0` were redefined inside NimBLE-Arduino 2.5.1. In `nimconfig.h`, the defaults are 3 connections and observer enabled. Its serial log said observer=OFF as literal text, without checking the effective macro. The prior build therefore did not prove the intended lean NimBLE configuration.

This revision sets `CONFIG_BT_NIMBLE_MAX_CONNECTIONS=2`, `CONFIG_BT_NIMBLE_ROLE_OBSERVER_DISABLED=1`, and `CONFIG_BT_NIMBLE_ATT_PREFERRED_MTU=247` in platformio.ini. `jk_ble_proxy.cpp` has compile-time assertions for effective `MYNEWT_VAL` values 2, 0 and 247 and prints those effective values during NimBLE init. It preserves the intended direct-connect diagnostic architecture. A future observer/scan feature needs a separate memory and coexistence review.

Evidence: PlatformIO 6.2.0, pinned espressif32 7.1.3 and dependencies; `pio run -e lilygo_tcan485 -t clean` PASS; `pio run -e lilygo_tcan485` compile and link PASS; no MYNEWT macro-redefinition warnings in that build. RAM 89,116/327,680 bytes (27.2%); program 1,538,909/1,835,008 bytes (83.9%). Compile-time assertions check the firmware translation unit; the actual connected ESP32 runtime, radio, coexistence and diagnostics remain untested here. A boot serial capture should show `compiled config maxConn=2 observer=0 mtu=247` when JK-BLE initialization is invoked.

The controlled A1/A2/C1/C2/D hardware matrix, heap/largest8, Wi-Fi/BLE coexistence, and security release gates remain open. No keys are included.
