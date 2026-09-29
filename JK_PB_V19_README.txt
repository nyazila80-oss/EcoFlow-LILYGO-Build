JK-PB1A16S10P V19.x adapter build
=================================
Target connection:
- JK physical port: RS485-1 / UART1
- JK UART1 protocol: 013 - (9600) JK BMS RS485 Modbus V1.0
- Serial: 9600 baud, 8N1
- JK Modbus address compiled here: 0x00

Changes from original JBD/Overkill project:
- JBD protocol parser replaced with JK-PB V19 55AA status parser.
- LilyGO actively triggers status register 0x1620 once per second using Modbus FC 0x10.
- Parses 300-byte 55 AA EB 90 02 00 status payload.
- Reads voltage, current, SOC, capacities, cell voltages, temperatures and MOS states.
- JK MOS writes remain disabled/read-only for safety.
- SPIFFS explicitly selected in platformio.ini.

Expected Serial Monitor after successful communication:
[JK-PB] Poll 0x1620 -> addr 0 @ 9600 baud
[JK-PB] V=...V I=...A SOC=...% T=...C cells=16 MOS C/D=1/1

If polls appear but no valid JK-PB line appears, verify the JK Device Address.
Change JK_MODBUS_ADDRESS in src/bms.cpp if the BMS address is not 0.
