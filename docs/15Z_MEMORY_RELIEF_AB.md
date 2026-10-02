# 9.36.7.15Z MEMORY-RELIEF A/B

Purpose: test whether the existing safe JK auxiliary reservation materially increases INTERNAL|8BIT headroom before EcoFlow TLS, without weakening TLS or globally deinitializing NimBLE.

A = INTERNAL|8BIT free/largest immediately before reservation attempt.
B = same measurements immediately after safe reservation/1 ms settle.

Reservation is attempted only when JK app disconnected, JK BMS disconnected, and no JK callback transition is pending. It is released after http.end(). If conditions are unsafe, A and B are still measured but BLE is untouched.

Interpretation:
- positive delta + later crypto improvement: memory/coexistence causality strengthened;
- near-zero delta: safe reservation alone does not reclaim the allocations responsible for 15Y pressure; do not infer that BLE is innocent;
- negative delta: reservation path itself consumes/perturbs memory; stop before stronger relief.

Safety invariants:
- no setInsecure();
- no VERIFY_NONE;
- no NimBLE global deinit;
- no cloud-write enablement;
- existing CA, credentials and request semantics unchanged;
- 15Y remains the control baseline.
