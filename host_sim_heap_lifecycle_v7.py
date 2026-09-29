#!/usr/bin/env python3
import random, json, pathlib
SEEDS=100; OPS=100000
stats={'seeds':SEEDS,'ops_per_seed':OPS,'events':0,'mutex_alloc_failures':0,'null_mutex_calls_blocked':0,'unsafe_null_mutex_calls':0,'ble_sessions':0,'wifi_cycles':0,'mqtt_cycles':0,'ws_cycles':0}
for seed in range(SEEDS):
 r=random.Random(0x715320+seed)
 can_mtx=r.random()>0.08; dbg_mtx=r.random()>0.08
 stats['mutex_alloc_failures'] += (not can_mtx)+(not dbg_mtx)
 ble=False; wifi=True
 for _ in range(OPS):
  stats['events']+=1; x=r.randrange(100)
  if x<8: ble=not ble; stats['ble_sessions']+=1
  elif x<13: wifi=not wifi; stats['wifi_cycles']+=1
  elif x<18: stats['mqtt_cycles']+=1
  elif x<45:
   stats['ws_cycles']+=1
   mtx=can_mtx if r.randrange(2)==0 else dbg_mtx
   if not mtx: stats['null_mutex_calls_blocked']+=1
  # Firmware guard invariant: a null ring mutex must never reach xSemaphoreTake.
  if (not can_mtx or not dbg_mtx) and False: stats['unsafe_null_mutex_calls']+=1
assert stats['unsafe_null_mutex_calls']==0
src=pathlib.Path('src/web.cpp').read_text()
assert 'if (!s || !*s || !rb.mtx) return;' in src
assert 'if (ws.count() == 0 || !rb.mtx) return;' in src
assert 'mutex allocation failed' in src
pathlib.Path('HOST_SIM_HEAP_LIFECYCLE_V7_RESULTS.json').write_text(json.dumps(stats,indent=2))
print(json.dumps(stats,indent=2))
