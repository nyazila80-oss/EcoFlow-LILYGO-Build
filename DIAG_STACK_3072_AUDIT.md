# DiagHeartbeat-Stack 3072: isolierter Hardware-Kandidat

Basis ist exakt NET-ROUTE-FIX. Änderungen: `diagAlive`-Stack von 2048 auf 3072 Byte; ein atomisch veröffentlichter Taskhandle erlaubt `diag_stack_min_bytes` in `/api/diag/ble-boot`. Diagnosekennung endet auf `DIAG-STACK-3072`. `FW_VERSION` und SPIFFS-Manifest bleiben gleich; kein Filesystem-Upload. RTC-Activity und WebUI-V2 sind nicht enthalten, damit ein Hardware-A/B-Vergleich isoliert bleibt.

Befund: COM4-Werte `stackRaw(diag/rx/dec)=264/2332/1172` (späterer Minimumwert im vorherigen Log) bei 2048-Byte-Diagnosetask. ESP-IDF v4.4 dokumentiert, dass `uxTaskGetStackHighWaterMark()` auf ESP32 Bytes liefert. 264 Byte Reserve ist niedrig; Stacküberlauf bleibt Hypothese, nicht als Panic-Ursache bewiesen. +1024 Byte Stack kostet etwa 1 KiB Heap; die neue HTTP-Messung erlaubt die Reserve auch ohne dauerhaftes USB zu verfolgen.

Prüfung hier: statischer Quell-/Versionsabgleich, kleiner C++11-Test der atomischen Taskhandle-Publikation. **Kein ESP32 Full Clean/Link/Hardwaretest in dieser Laufzeit.** Windows im entpackten Projektordner: `powershell -ExecutionPolicy Bypass -File .\Build-STACK-DIAG-Windows.ps1`. Das Skript bereinigt und baut, zeigt aufgelöste Pakete und Hashes; kein Upload. Die Logs vor Weitergabe auf lokale Zugangsdaten prüfen.

Gates nach erfolgreichem ESP32-Build: Firmware-OTA nur für `firmware.bin`, nicht SPIFFS. Direkt nach Boot muss `diag_version` die neue Kennung und `diag_stack_min_bytes` einen plausiblen Wert zeigen. Danach Zeitfenster mit gleichen WebUI/JK-BLE-Bedingungen beobachten und Resetgrund/Heap/WiFi/BLE vergleichen. Eine ausbleibende Panic in kurzer Laufzeit ist keine Ursachenbestätigung. Bis zur Hardwareevidenz keine PowerStream-Connect/Auth/Schreibtests.
