# Netzwerkdiagnose für BLE-Start (Testkandidat)

Nach OTA-Upload `http://192.168.178.67/api/diag/ble-boot` im VPN öffnen, zunächst vor und danach mindestens 60 Sekunden nach dem Start erneut abrufen. JSON samt Uhrzeit und eventuell erneutem Reboot senden. `ms` zählt Millisekunden seit dem aktuellen Boot.

`current_stage` und `previous_stage` bedeuten: 0 BLE-Initialisierung noch nicht erreicht; 1 Vorprüfung; 2 WiFi-Modem-Sleep-Treiberprüfung bestanden; 3 Eintritt in `NimBLEDevice::init`; 4 Rückkehr daraus; 5 virtuelles JK wird beworben. `previous_stage` stammt aus RTC-Speicher des letzten Boots, sofern gültig. `reset_reason` ist die ESP-IDF-Nummer der Neustartursache. Nach vollständigem Stromverlust kann der vorherige Status verloren sein.

Der Endpunkt enthält bewusst keinen vollständigen Serial-Log oder Backtrace. Besonders bei schneller Reset-Schleife oder fehlender Netzwerkverbindung bleibt der USB-Serial-Monitor zur Fehleranalyse nötig. HTTP-Diagnose ist im Heimnetz/VPN lesbar und sollte nicht über Router-Portfreigaben veröffentlicht werden. Kein automatisches Firmware- oder SPIFFS-Update erfolgt durch dieses Paket.

Build: `pio run -e lilygo_tcan485`; OTA mit lokal hinterlegtem Passwort: `pio run -e lilygo_tcan485_ota -t upload`. Partitionstabelle und SPIFFS nicht per OTA ändern.
