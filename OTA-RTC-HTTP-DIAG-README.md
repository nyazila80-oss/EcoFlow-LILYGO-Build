# OTA-Diagnosekandidat: RTC-HTTP-Aktivität

Diese Version baut auf `...DIAG-STACK-3072` auf. Sie schreibt beim Aufruf von vier HTTP-Routen einen kleinen Zustandsmarker in RTC-RAM und zeigt dessen vorherigen Wert nach einem Neustart unter `/api/diag/ble-boot` an. Es wird weder die Partitionstabelle noch SPIFFS geändert.

## Build und OTA ohne USB

1. Den Ordner öffnen, der diese Datei und `platformio.ini` enthält.
2. `Build-STACK-DIAG-Windows.ps1` im VS-Code-Terminal ausführen. Falls PowerShell die Ausführung blockiert, nur für diesen Prozess: `powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\Build-STACK-DIAG-Windows.ps1`. Nur bei `Build complete` und `SUCCESS` fortfahren.
3. Auf `http://192.168.178.67/ota_update` im Feld **OTA firmware upload** genau `.pio/build/lilygo_tcan485_ota/firmware.bin` aus diesem Ordner auswählen. Nicht `spiffs.bin` auswählen und keinen PlatformIO-Upload-Task ausführen.
4. Nach dem Neustart `/api/diag/ble-boot` lesen. Erwartete `diag_version` endet auf `DIAG-STACK-3072-RTC-HTTP`.

Der bisher beobachtete Reset `reset_reason=4` bleibt ungeklärt. Bis zur Auswertung keine PowerStream-BLE-Tests C/D, keine Priority-Befehle. Bei einem weiteren spontanen Neustart die vollständige Antwort von `/api/diag/ble-boot` und `/api/net/health` sichern.

## Interpretation

- `previous_http_active_mask`: Bit 0 `/api/bms`, Bit 1 PowerStream-BLE-Status, Bit 2 statische Seite, Bit 3 `/api/net/health`. Ein gesetztes Bit besagt, dass der synchrone Callback beim Reset noch aktiv war; es beweist keine Ursache. Null schließt Fehler in asynchronen Netzwerk-Tasks nicht aus.
- `previous_http_last_route`: letzte betretene dieser Routen, 1 bis 4. Ist auch nach Verlassen der Route gesetzt.
- `previous_http_free_heap`, `previous_http_largest8`, `previous_http_at_ms`: Momentaufnahme beim Betreten dieser Route, keine Crash-Werte.
- `diag_stack_min_bytes`: bisheriger Stack-Wassermarkenwert seit dem aktuellen Start, kein Wert aus dem letzten Absturz.

Der Code aktiviert keinen ESP-IDF-Coredump. Die reservierte `coredump`-Partition allein belegt nicht, dass ein Dump geschrieben wird. Die RTC-Marker liefern keinen Backtrace oder eine genaue Absturzadresse.
