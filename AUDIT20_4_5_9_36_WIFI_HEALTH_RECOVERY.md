# 20.4.5.9.36 WIFI HEALTH RECOVERY
Hardware trigger: runtime HTTP/remote unreliability, uploadfsota 0% failures, ERR_ADDRESS_UNREACHABLE; uploadfsota succeeded immediately after power-cycle.
Finding: recovery accepted WL_CONNECTED without requiring a usable non-zero local IPv4 address.
Changes: staHasUsableIp(); startSTA/ensureWiFi stronger health predicate; explicit autoReconnect; 9.35 U_SPIFFS fix retained. Existing 10s/30s/120s recovery design retained. CAN/BMS/BLE/SOC safety semantics unchanged.
Limitation: does not prove hardware root cause; stale non-zero IP/TCPIP wedge/main-loop stall still require runtime evidence.
