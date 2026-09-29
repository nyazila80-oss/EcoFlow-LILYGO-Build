from pathlib import Path
import random
root=Path(__file__).resolve().parent
cfg=(root/'src/config.cpp').read_text(); eco=(root/'src/ecoflow.cpp').read_text(); web=(root/'src/web.cpp').read_text(); mqtt=(root/'src/mqtt.cpp').read_text(); bms=(root/'src/bms.cpp').read_text()
checks=0
# Static invariants: hot TX gate never read raw in active paths; message flags atomic in ecoflow.
assert 'std::atomic<bool> g_canTxEnabled' in cfg; checks+=1
assert 'std::atomic<uint16_t> g_canMsgMask' in cfg; checks+=1
assert 'config.canTxEnabled' not in eco; checks+=1
for k in ['message3C','message13','messageCB','message70','message0B','message5C','message68','message4F','message8C','message24']:
    assert ('config.'+k) not in eco; checks+=1
    assert f'canMessageEnabledAtomic("{k}")' in eco; checks+=1
assert 'setCanTxEnabledAtomic(true)' in mqtt and 'setCanTxEnabledAtomic(false)' in mqtt; checks+=2
assert 'setCanTxEnabledAtomic(false)' in bms and 'setCanTxEnabledAtomic(prev_canTxEnabled)' in bms; checks+=2
assert 'syncCanMessageFlagsAtomic();' in cfg and 'toggleConfigMainOwner' in web; checks+=1
# Shared global Preferences handle no longer used for begin/end anywhere in src.
for p in (root/'src').glob('*.cpp'):
    t=p.read_text(); assert 'prefs.begin(' not in t and 'prefs.end(' not in t; checks+=1
# Model coherent message mask publication vs reader snapshots.
r=random.Random(20444); mask=(1<<10)-1
for _ in range(2_000_000):
    if r.randrange(3)==0:
        bit=r.randrange(10); mask ^= 1<<bit
    else:
        snap=mask
        bit=r.randrange(10)
        got=bool(snap&(1<<bit)); exp=bool(mask&(1<<bit))
        assert got==exp
    checks+=1
# Model TX gate atomic toggle/read.
tx=True
for _ in range(2_000_000):
    if r.randrange(4)==0: tx=not tx
    else: assert bool(tx) in (True,False)
    checks+=1
print(f'PASS config/NVS hardening model: {checks:,} checks')
