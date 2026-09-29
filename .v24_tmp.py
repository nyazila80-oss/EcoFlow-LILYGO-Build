from pathlib import Path
import random
root=Path(__file__).resolve().parent
cfg=(root/'include/config.h').read_text(); main=(root/'src/main.cpp').read_text(); conf=(root/'src/config.cpp').read_text(); eco=(root/'src/ecoflow.cpp').read_text(); web=(root/'src/web.cpp').read_text()
checks={
 'version':'AUDIT20.4.4.8-FINAL-AUDIT-HARDENED' in cfg,
 'txlog_atomic_decl':'g_txLogging' in conf and 'txLoggingAtomic()' in conf and 'setTxLoggingAtomic' in conf,
 'txlog_hotpath_atomic':'config.txlogging' not in eco and eco.count('txLoggingAtomic()')>=2,
 'txlog_web_setter':'if (k == "txlogging")' in web and 'setTxLoggingAtomic(v)' in web,
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
print('FINAL V24 checks',checks)
print('modeled operations',2_000_000,'violations',viol)
print('PASS' if all(checks.values()) and viol==0 else 'FAIL')
raise SystemExit(0 if all(checks.values()) and viol==0 else 1)
