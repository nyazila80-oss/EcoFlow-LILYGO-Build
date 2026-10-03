#!/usr/bin/env python3
from pathlib import Path

p = Path('src/powerstream_api.cpp')
s = p.read_text()
# Remove the ESP8266/BearSSL-only API accidentally introduced by the first 15AL attempt.
s = s.replace('  client.setBufferSizes(8192, 4096);\n', '')
s = s.replace('  client.setBufferSizes(8192, 4096);\r\n', '')
p.write_text(s)
print('[15AL] unsupported WiFiClientSecure::setBufferSizes removed; buffer sizing is compile-time on ESP32 mbedTLS')
