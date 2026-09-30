# 9.36.7.15H — X.509 / TLS FMEA gate

Hardware observation motivating this diagnostic:

- With BLE/NimBLE active, cloud TLS failed on a 16,717-byte INTERNAL/8BIT allocation.
- With BLE startup disabled, the large allocation failure disappeared and the handshake progressed to `MBEDTLS_ERR_X509_CERT_VERIFY_FAILED` (-9984).
- During that run the failed-allocation hook later observed INTERNAL/8BIT near exhaustion, so certificate failure and memory pressure must be separated before changing trust configuration.

## Failure modes and 15H evidence

1. **ESP32 clock invalid/stale** — certificate validity check can fail. Evidence: `tls_epoch_pre/post`, `tls_time_sane_pre/post`.
2. **CA/chain/signature verification failure with sane clock** — keep CA verification enabled and investigate the configured trust chain; do not use `setInsecure()`.
3. **INTERNAL RAM exhaustion during certificate verification** — evidence: `tls_internal_pre_verify_*`, `tls_internal_post_verify_*` plus the existing failed-allocation capability snapshot.
4. **BLE/NimBLE coexistence pressure** — compare the same 15H transaction first with BLE startup disabled, then enabled; do not change other variables.
5. **Credential/HMAC issue** — existing 15D provenance fields remain available and raw credentials remain unexported.

## Safety gates

- `client.setCACert(ECOFLOW_CA_BUNDLE)` must remain present.
- `setInsecure()` is forbidden.
- 15H adds diagnostics only; it does not enable cloud writes.
- Do not intentionally disconnect the JK/BMS link as part of the X.509 diagnosis.
- Do not conclude that the CA is wrong from `-9984` alone; first inspect clock and INTERNAL-memory evidence.

## Hardware acceptance sequence

A. Boot with BLE startup disabled and confirm `ble_initialized=false`.
B. Run exactly one PowerStream cloud read.
C. Capture the full cloud-job JSON including the new 15H fields and existing failed-allocation fields.
D. Classify the failure using clock + memory evidence.
E. Only after A-D, repeat with BLE enabled for the controlled coexistence comparison.
