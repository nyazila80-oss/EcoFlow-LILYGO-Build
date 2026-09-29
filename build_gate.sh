#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
if ! command -v pio >/dev/null 2>&1; then
  echo 'PlatformIO (pio) is not installed in PATH.' >&2
  exit 2
fi
pio run -e lilygo_tcan485_ota -t clean
pio run -e lilygo_tcan485_ota
python3 - <<'PY'
from pathlib import Path
from hashlib import sha256
import json
source = Path('src/web.cpp').read_text()
binpath = Path('.pio/build/lilygo_tcan485_ota/firmware.bin')
marker = b'PS-AUTH-V3-ONLY'
assert marker.decode() in source, 'source version marker missing'
blob = binpath.read_bytes()
assert marker in blob, 'built BIN lacks version marker'
print(json.dumps({
  'source_marker': marker.decode(),
  'firmware_path': str(binpath.resolve()),
  'size_bytes': len(blob),
  'sha256': sha256(blob).hexdigest(),
}, indent=2))
PY
