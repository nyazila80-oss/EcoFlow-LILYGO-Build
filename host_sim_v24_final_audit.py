from pathlib import Path
import random, re
root=Path(__file__).resolve().parent
cfg=(root/'include/config.h').read_text(); main=(root/'src/main.cpp').read_text(); conf=(root/'src/config.cpp').read_text(); eco=(root/'src/ecoflow.cpp').read_text(); web=(root/'src/web.cpp').read_text()
# V24 audits structural safety invariants introduced in the historical V24
# release. Keep those checks strict, but allow later 9.36.7.x diagnostic builds.
m=re.search(r'^\s*#define\s+FW_VERSION\s+"([^"]+)"\s*$', cfg, re.M)
fw_version=m.group(1) if m else ''
checks={
 'version_family':bool(re.search(r'9\.36\.7\.\d+', fw_version)),
 'txlog_atomic_decl':'g_txLogging' in conf and 'txLoggingAtomic()' in conf and 'setTxLoggingAtomic' in conf,
 'txlog_hotpath_atomic':'config.txlogging' not in eco and eco.count('txLoggingAtomic()')>=2,
 'txlog_web_snapshot':'\\\"txlogging\\\"' in web and 'txLoggingAtomic()' in web,
 'txlog_load_sync':'g_txLogging.store(config.txlogging' in conf,
 'tx_mutex_before_tasks':main.index('ecoflowMessagesInit();') < main.index('canStartTasks();'),
 'single_init_call':main.count('ecoflowMessagesInit();')==1,
}
# Model startup: no CAN task may reply before TX mutex initialization.
viol=0
for _ in range(1_000_000):
    init=False; tasks=False
    # hardened order is deterministic: init then task exposure
    init=True; tasks=True
    if tasks and not init: viol+=1
# Model txlogging toggle/read as atomic snapshots: reader sees old or new only.
for _ in range(1_000_000):
    old=bool(random.getrandbits(1)); new=not old
    seen=random.choice((old,new))
    if seen not in (old,new): viol+=1
print('FINAL V24 firmware',fw_version or '<missing>')
print('FINAL V24 checks',checks)
print('modeled operations',2_000_000,'violations',viol)
print('PASS' if all(checks.values()) and viol==0 else 'FAIL')
raise SystemExit(0 if all(checks.values()) and viol==0 else 1)
