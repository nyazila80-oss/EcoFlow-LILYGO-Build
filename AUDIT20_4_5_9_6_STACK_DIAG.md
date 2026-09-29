# AUDIT20.4.5.9.6 — Stack diagnostics correction

Deep audit finding: ESP-IDF on ESP32 documents `uxTaskGetStackHighWaterMark()` as returning the minimum free stack in bytes. Version 9.5 multiplied that value by `sizeof(StackType_t)`, potentially over-reporting the margin by 4x. Version 9.6 removes that multiplication.

No CAN or low-SOC guard behavior is changed. PowerStream BLE remains manual one-shot only.

Additional audit notes:
- PowerStream HW51 working reference uses GATT UUIDs 00000001/02/03; retained.
- NimBLE 2.5.1 supports two client objects; shared arbiter remains capped at two active BLE connections.
- PS worker stack remains 6144 bytes; actual minimum-free value must be measured on hardware before SOC automation.
- PlatformIO build is still not verified in this environment.
