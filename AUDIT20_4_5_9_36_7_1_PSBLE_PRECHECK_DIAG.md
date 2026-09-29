# AUDIT20.4.5.9.36.7.1 — PS BLE precheck diagnostics

Diagnostics-only change around the existing manual PowerStream BLE one-shot start path. Pre-connect rejection is persisted to last_error; status exposes JK init, JK-BMS core link, JK-app-free, Wi-Fi stable, heap, cooldown, and heavy-resource prechecks. WebUI renders OK/BLOCK. No GATT/auth/command/CAN/RS485/JK protocol/SOC guard semantics changed. Firmware and filesystem versions synchronized.
