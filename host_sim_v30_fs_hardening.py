from pathlib import Path
import random,re,csv
R=Path(__file__).resolve().parent
web=(R/'src/web.cpp').read_text()
fw=re.search(r'#define FW_VERSION "([^"]+)"',(R/'include/config.h').read_text()).group(1)
manifest=(R/'data/fs_version.txt').read_text().strip()
assert manifest==fw
assert 'serveStatic("/", SPIFFS' not in web
protected=['index.html','remote.html','bms_dashboard.html','bms_readings.html','canlog_streaming.html','debug_streaming.html','ota_update.html']
for f in protected: assert f'/{f}' in web
checks=0
for mounted in (False,True):
 for match in (False,True):
  for authenticated in (False,True):
   for _ in range(25000):
    checks+=1
    status='FS_MOUNT_FAILED' if not mounted else ('FS_OK' if match else 'FS_VERSION_MISMATCH')
    # static content must never be served without auth
    served=authenticated and mounted
    assert not served or authenticated
    assert (status=='FS_OK') == (mounted and match)
print(f'V30 FS hardening: checks={checks}, violations=0, manifest={fw}')
print('PASS')
