# PowerStream BLE: Auth-Version-3-Diagnose

Dieser **separate, manuelle Lab-Build** beruht auf dem erfolgreichen NVS-FIRSTOPEN-TRACECOUNTS-Quellstand. Er prüft isoliert, ob die Protokollversion des Auto-Auth-Pakets den 0x04-Rückgabecode beeinflusst. Die vorherige Firmware sendete Auth-Status mit Version 3, Auto-Auth mit Version 2; der PowerStream meldete Status-Antwortversion 3 und Auth-Antwortversion 2/Code 0x04. Hier verwenden beide ausgehenden Pakete Version 3. User-ID und vollständige Geräte-S/N werden unverändert zu MD5(User-ID + S/N) verarbeitet; BLE-MAC, UID, SN, GATT, AES und CAN bleiben unverändert.

`PS_AUTH_V3_PROBE_ONLY=1` im Build. Im HTTP-Pfad und im Worker sind Storage-/Supply-Priority-Schreibvorgänge gesperrt. Nur der Button `C: Connect + GATT + Auth testen` ist für diese Variante vorgesehen. Keine automatische Wiederverbindung oder SOC-Steuerung. OTA/Web/JK/RS485/CAN und SPIFFS-Inhalt bleiben wie im Basisstand.

Nach einem OTA-Upload zuerst `/api/diag/ble-boot` auf `PS-AUTH-V3-ONLY` prüfen und A/B-Stabilität abwarten. Vor einem einzigen C-Test `/api/net/health` und `/api/powerstream/ble-lab/status` sichern. Danach erneut Status, BLE-Boot-Diagnose und WLAN-Diagnose sichern. `auth_request_version` muss 3 anzeigen. Bei `0x04` bleibt eine Bindungs-/Geräteprotokoll-Frage offen; erneutes Binden in der offiziellen App ist eine separat zu bewertende Maßnahme und wird durch diesen Test nicht automatisch durchgeführt. Kein D-Test mit dieser Firmware.

Quellenvergleich: rabits/ha-ef-ble, Commit 89fa21c113f38640b65fdaa9329a918a14d9efd3, `connection.py` nutzt für Status und Auth dieselbe `_packet_version`, und `devicebase.py` setzt sie standardmäßig auf 0x03. Ein dokumentierter PowerStream-Fall meldet 0x04 auch bei Version 3; das Ergebnis ist deshalb nicht vorweggenommen.

Der Test ist erst nach einem erfolgreichen Clean-Build und anschließendem Hardwaretest aussagekräftig. Das SPIFFS-Systemimage ist unverändert und muss nicht erneut hochgeladen werden.

Build-Nachweis 27.09.2026: Host-NVS-Test PASS; OTA-Umgebung nach Clean erfolgreich kompiliert und gelinkt. RAM 89.332/327.680 Byte (27,3 %), Flash 1.556.633/1.835.008 Byte (84,8 %). BIN 1.563.216 Byte, SHA-256 `13f9595ced171e285591c7325b24a535937cf25ff6371bea70b2ff033f03890a`. Hardwarewirkung und Auth-Erfolg sind offen.
