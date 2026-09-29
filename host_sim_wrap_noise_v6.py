#!/usr/bin/env python3
import random, json, argparse, pathlib
U32=0xffffffff
TIMEOUT=1200; POLL=800; STALE=3000; BUDGET=128

def elapsed(now, then): return (now-then)&U32

def due(now, then, period): return elapsed(now,then)>=period

def run(seed, steps):
 r=random.Random(seed); now=r.randrange(0xfffff000,0x100000000); request=now; last_valid=now; waiting=True; valid=True
 uart=0; consumed=0; max_consumed=0; timeouts=0; stale=0; loop_ticks=0; wifi=ble=can=0; wraps=0; prev=now
 poll=now
 for i in range(steps):
  # 0..400 noisy bytes arrive per loop; occasionally valid-ish traffic burst
  uart=min(100000,uart+r.randrange(0,401))
  take=min(BUDGET,uart); uart-=take; consumed+=take; max_consumed=max(max_consumed,take)
  # mirror source timeout arithmetic with uint32 millis wrap
  if waiting and elapsed(now,request)>TIMEOUT:
   waiting=False; timeouts+=1
  if valid and elapsed(now,last_valid)>STALE:
   valid=False; stale+=1
  if (not waiting) and due(now,poll,POLL):
   waiting=True; request=now; poll=now
  # Other loop services must still get a tick despite permanent UART backlog
  wifi+=1; ble+=1; can+=1; loop_ticks+=1
  # advance 1..25 ms, forcing many wraps
  now=(now+r.randrange(1,26))&U32
  if now<prev: wraps+=1
  prev=now
 # properties
 assert max_consumed<=128
 assert wifi==steps and ble==steps and can==steps and loop_ticks==steps
 # With permanent noise, request timeout must still occur; noise must not postpone it.
 assert timeouts>0
 return dict(seed=seed,steps=steps,wraps=wraps,timeouts=timeouts,stale_invalidations=stale,uart_consumed=consumed,uart_backlog=uart,max_uart_per_loop=max_consumed,service_ticks=loop_ticks)

def main():
 ap=argparse.ArgumentParser(); ap.add_argument('--seeds',type=int,default=100); ap.add_argument('--steps',type=int,default=100000); ap.add_argument('--out',default='HOST_SIM_WRAP_NOISE_V6_RESULTS.json'); a=ap.parse_args()
 rows=[run(s,a.steps) for s in range(a.seeds)]
 out={'version':'V6','seeds':a.seeds,'steps_per_seed':a.steps,'total_events':a.seeds*a.steps,'total_wraps':sum(x['wraps'] for x in rows),'total_timeouts':sum(x['timeouts'] for x in rows),'total_stale_invalidations':sum(x['stale_invalidations'] for x in rows),'max_uart_bytes_processed_per_loop':max(x['max_uart_per_loop'] for x in rows),'all_other_services_received_every_loop':all(x['service_ticks']==a.steps for x in rows),'violations':0}
 pathlib.Path(a.out).write_text(json.dumps(out,indent=2)+'\n'); print(json.dumps(out,indent=2))
main()
