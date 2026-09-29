# Network health route fix (9.36.7.11)

ESPAsyncWebServer 3.12.1 treats a plain `/api/net` handler as matching both `/api/net` and subpaths such as `/api/net/health`. Because the short handler was registered first, the health URL returned the short STA/IP/SSID JSON.

The GET and POST `/api/net` handlers and GET `/api/net/health` now use `AsyncURIMatcher::exact`. The BLE diagnostic marker is `9.36.7.11-BLE-HTTP-STATUS-NET-ROUTE-FIX`.

Build target: `lilygo_tcan485_ota`. Upload firmware only; no SPIFFS image. After OTA, check `/api/diag/ble-boot` for the new marker, then `/api/net/health` for `wifi_status`, `reconnects`, `heap`, and `min_heap`. The existing `/api/net` should still return `mode`, `ip`, and `ssid`.

Local compile/link succeeded. HTTP behavior must be confirmed on the board after OTA.
