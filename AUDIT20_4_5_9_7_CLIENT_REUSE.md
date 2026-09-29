# AUDIT20.4.5.9.7 — PowerStream BLE client reuse / disconnect barrier

- Dedicated PS NimBLEClient is retained across one-shot operations to reuse cached GATT attributes and reduce heap churn.
- Graceful disconnect is requested and boundedly observed before the JK auxiliary connection reservation is released.
- If disconnect remains active after 1200 ms, documented NimBLEDevice::deleteClient() hard cleanup is used.
- Configuration identity changes invalidate/delete the cached PS client while the config admission gate excludes the worker.
- BLE_MAX_CONNECTIONS remains 2; the retained but disconnected PS client does not itself consume an active BLE connection.
- Existing CAN and low_soc_guard source unchanged.
