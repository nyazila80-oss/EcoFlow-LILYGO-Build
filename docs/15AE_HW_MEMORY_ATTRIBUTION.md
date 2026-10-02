# 15AE — real-hardware TLS memory attribution

Real LILYGO evidence: mbedTLS requested a contiguous **16,717-byte** allocation while largest INTERNAL|8BIT was **10,740** and **13,812 bytes** in two failed runs. Aggregate heap was substantially larger. Credentials matched NVS/request snapshots and Wi-Fi stayed connected.

The second run reported `tls15z_stop_observed=false` and `tls15z_slot_ready_pre_tls=false`; therefore the existing reclaim is not yet proven to stop/release the intended BLE resource before TLS.

## Rules
- Keep CA verification fail-closed.
- Do not globally disable JK-BLE/NimBLE merely to pass HTTPS.
- Do not treat a preflight threshold change as a root-cause fix.
- Preserve failed-allocation telemetry.
- Attribute contiguous-block loss across client/CA/begin/auth/GET before lifecycle changes.
- PowerStream BLE auth `0x04` remains a separate issue.

## Exit criterion
A real LILYGO must complete a verified EcoFlow HTTPS request without allocation failure, with telemetry demonstrating why the required contiguous block remained available. Host/build PASS alone cannot close 15AE.
