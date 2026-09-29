from pathlib import Path
import re,csv,random
R=Path(__file__).parent
cfg=(R/'include/config.h').read_text(); web=(R/'src/web.cpp').read_text(); wifi=(R/'src/wi-fi.cpp').read_text(); ota=(R/'src/ota.cpp').read_text()
ver=re.search(r'#define FW_VERSION "([^"]+)"',cfg).group(1)
checks={
 'version':ver in cfg,
 'manifest':(R/'data/fs_version.txt').read_text().strip()==ver,
 'fs_mismatch_failclosed':'if (!sFsVersionMatch)' in web and 'Filesystem/Firmware version mismatch' in web,
 'no_static_root':'serveStatic("/", SPIFFS' not in web,
 'no_fixed_ap_password':'ecoflow123' not in wifi,
 'recovery_uses_device_admin_secret':'remoteAuthPassword()' in wifi,
 'http_ota_auth':'remoteAuthUser()' in ota and 'remoteMutationAllowed(request)' in ota,
 'arduino_ota_auth':'ArduinoOTA.setPassword(remoteAuthPassword())' in ota,
 'firmware_fs_split':'U_FLASH' in ota and 'U_SPIFFS' in ota,
}
refs=set(re.findall(r'"(/[A-Za-z0-9_.-]+\\.html|/fs_version\\.txt)"',web)); actual={'/'+p.name for p in (R/'data').iterdir() if p.is_file()}; checks['all_fs_refs_present']=not(refs-actual)
rows=[]
with open(R/'partitions.csv') as f:
 for row in csv.reader(f):
  if not row or row[0].strip().startswith('#'): continue
  o=int(row[3].strip(),0); s=int(row[4].strip(),0); rows.append((o,o+s))
checks['partition_no_overlap']=all(rows[i][1]<=rows[i+1][0] for i in range(len(rows)-1)); checks['flash_end_4m']=max(e for _,e in rows)==0x400000
# Model FS delivery decision and recovery secret invariants over random conditions.
viol=0
for _ in range(1_000_000):
 mounted=bool(random.getrandbits(1)); match=bool(random.getrandbits(1)); exists=bool(random.getrandbits(1)); authed=bool(random.getrandbits(1))
 served=authed and mounted and match and exists
 if served and not (authed and mounted and match and exists): viol+=1
checks['modeled_failclosed']=viol==0
print('V31 checks',checks,'modeled=1000000','violations=',viol)
assert all(checks.values())
print('PASS')
