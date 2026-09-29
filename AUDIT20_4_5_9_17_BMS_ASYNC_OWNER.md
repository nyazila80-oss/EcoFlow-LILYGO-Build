# AUDIT20.4.5.9.17 — BMS ASYNC OWNER / MUTEX / SNAPSHOT HARDENING

Addressed findings:
- AsyncWebServer no longer directly mutates JKPBBms. Setup refresh and safe setting writes use a FREE→WRITING→READY handoff and are executed by `webTick()` on the main-loop owner.
- A BMS object mutex now serializes parser/request mutation with the legacy deep HTTP diagnostic readers, eliminating the C++ data race on JKPBBms fields. The lock is intentionally not used by CAN safety gating; safety uses the atomic snapshot.
- BMS safety snapshot extended coherently with SOH, voltage and temperature. MQTT, BMS WebSocket and low-SOC status use this immutable atomic snapshot instead of live mutable JKPBBms fields.
- BMS diagnostic counters changed from `volatile` to `std::atomic<uint32_t>`.

Residual performance concern:
- `/api/bms` and `/api/bms/full` still build relatively large JSON while holding the BMS object mutex. This is race-free but can delay a JK parser/poll transaction if the HTTP task holds the lock for too long. Next audit should replace this with a main-loop-published diagnostic cache so HTTP never locks the live BMS object.

Automatic SOC control remains OFF. No successful PlatformIO compile or hardware validation is claimed.
