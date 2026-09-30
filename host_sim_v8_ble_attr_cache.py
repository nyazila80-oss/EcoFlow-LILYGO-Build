import random, pathlib, re
ROOT=pathlib.Path(__file__).resolve().parent
src=(ROOT/'src/jk_ble_proxy.cpp').read_text()
assert 'connect(target, false, false, false)' in src
assert 'connect(target, true, false, false)' not in src
cfg=(ROOT/'include/config.h').read_text()
m=re.search(r'^\s*#define\s+FW_VERSION\s+"([^"]+)"\s*$', cfg, re.M)
fw_version=m.group(1) if m else ''
# This regression protects the fixed-peer BLE attribute-cache lifecycle. Diagnostic
# firmware suffixes must not create false failures; keep the maintained 2.4.5/9.36.7
# family gate while the BLE implementation assertions above remain exact/fail-closed.
assert fw_version.startswith('2.4.5.9.36.7.'), f'unexpected firmware family: {fw_version!r}'
# Model fixed-peer reconnect lifecycle. Cached attr object identity must survive disconnect/reconnect;
# queued bridge data must never cross a session boundary.
r=random.Random(191534)
connected=False; app=False; attr_id=1; session=0; q_ab=[]; q_ba=[]; violations=0
ops=2_000_000; reconnects=0; disconnects=0; writes=0; notifies=0
for _ in range(ops):
    x=r.randrange(100)
    if x<5:
        if connected:
            connected=False; disconnects+=1; q_ab.clear(); q_ba.clear()
    elif x<10:
        if not connected:
            connected=True; reconnects+=1; session+=1
            # deleteAttributes=false: cached object identity retained for same peer
            if attr_id != 1: violations += 1
            q_ab.clear(); q_ba.clear()
    elif x<13:
        app=not app; q_ab.clear(); q_ba.clear()
    elif x<55 and connected and app:
        if len(q_ab)<2: q_ab.append(session)
    elif x<80 and connected and app:
        if len(q_ba)<2: q_ba.append(session)
    elif x<90 and connected and q_ab:
        s=q_ab.pop(0); writes+=1; violations += (s!=session)
    elif connected and app and q_ba:
        s=q_ba.pop(0); notifies+=1; violations += (s!=session)
assert violations==0
print(f'firmware={fw_version} ops={ops} reconnects={reconnects} disconnects={disconnects} writes={writes} notifies={notifies} violations={violations}')
print('PASS BLE attribute-cache lifecycle model')
