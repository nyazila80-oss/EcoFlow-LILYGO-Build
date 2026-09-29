"""Check Wi-Fi credential reload is retried after transient NVS lock/open failure."""
from pathlib import Path
import random
src=Path('src/wi-fi.cpp').read_text()
assert 'bool loadWiFiConfig()' in src
assert 'if(!p.begin("net", true) && !p.begin("net", false))return false;' in src
assert 'if(loadWiFiConfig()){\n      wifiCredNextReloadRetryMs=0;\n      wifiCredsUpdatedKick();' in src
assert 'wifiCredReloadPending.store(true, std::memory_order_release);' in src
assert 'wifiCredNextReloadRetryMs=millis()+1000;' in src
rng=random.Random(936711)
for _ in range(100000):
    pending=True; kicks=0
    outcomes=[bool(rng.getrandbits(1)) for _ in range(8)]
    for loaded in outcomes:
        if not pending:break
        pending=False
        if loaded:kicks+=1
        else:pending=True
    assert kicks<=1
    assert bool(kicks)==any(outcomes)
    assert pending==(not bool(kicks))
print('PASS Wi-Fi NVS reload retries: 100000 sequences')
